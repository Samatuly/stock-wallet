"""Разбор CSV из брокерского отчёта или из Excel в список позиций.

Колонки находятся по названию (английскому или русскому), порядок не важен.
Обязательные: тикер, количество, цена покупки, дата. Остальное необязательно.
Ничего не угадываем молча там, где можно ошибиться: например, дата 03/04/2026
неоднозначна (3 апреля или 4 марта?), и такая строка помечается ошибкой с просьбой
использовать формат ГГГГ-ММ-ДД или ДД.ММ.ГГГГ.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Optional

from pydantic import ValidationError

from app.schemas import PositionCreate

ALIASES = {
    "ticker": {"ticker", "symbol", "тикер", "символ", "код", "бумага"},
    "quantity": {"quantity", "qty", "shares", "amount", "количество", "кол-во", "колво", "штук"},
    "buy_price": {"buy_price", "price", "avg_price", "average_price", "cost_basis_per_share", "цена", "цена покупки", "цена_покупки", "средняя цена"},
    "buy_date": {"buy_date", "date", "trade_date", "purchase_date", "дата", "дата покупки", "дата_покупки"},
    "market": {"market", "рынок"},
    "currency": {"currency", "валюта"},
    "fee": {"fee", "commission", "fees", "комиссия"},
    "note": {"note", "notes", "comment", "комментарий", "заметка"},
}

EU_SUFFIXES = (".DE", ".PA", ".L", ".AS", ".MI", ".MC", ".SW", ".BR", ".VI", ".ST", ".HE", ".CO", ".OL", ".LS", ".F")
DEFAULT_CURRENCY = {"US": "USD", "EU": "EUR", "KZ": "KZT"}


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().lower().replace("﻿", ""))


def _map_headers(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, h in enumerate(headers):
        name = _norm_header(h)
        for field, names in ALIASES.items():
            if name in names and field not in mapping:
                mapping[field] = idx
    return mapping


def parse_number(raw: str) -> float:
    """'1 234,56', '1,234.56', '12,5' -> float. Бросает ValueError, если не число."""
    s = raw.strip().replace("\xa0", "").replace(" ", "")
    s = re.sub(r"[^\d,.\-]", "", s)  # символы валют
    if not s or s in {"-", ".", ","}:
        raise ValueError(f"не число: {raw!r}")
    if "," in s and "." in s:
        # последний разделитель считаем десятичным
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def parse_date(raw: str) -> date:
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        a, b, year = int(m[1]), int(m[2]), int(m[3])
        if a > 12:
            return date(year, b, a)  # 25/03/2026: первое число — точно день
        if b > 12:
            return date(year, a, b)  # 03/25/2026: второе число — точно день
        raise ValueError(f"дата {raw!r} неоднозначна (день/месяц или месяц/день), используйте ГГГГ-ММ-ДД или ДД.ММ.ГГГГ")
    raise ValueError(f"не удалось распознать дату {raw!r}, используйте ГГГГ-ММ-ДД или ДД.ММ.ГГГГ")


# Названия бирж и стран, которые встречаются в отчётах брокеров (Freedom, Halyk, Tabys и др.)
MARKET_ALIASES = {
    "KZ": ("KASE", "AIX", "KZ", "KAZ", "КАЗАХСТАН", "КАСЕ", "МФЦА", "AIFC"),
    "US": ("NYSE", "NASDAQ", "AMEX", "ARCA", "US", "USA", "США", "ITS", "SPB"),
    "EU": ("XETRA", "LSE", "EURONEXT", "FRANKFURT", "EU", "ЕВРОПА", "EUROPE", "LSE", "SIX", "BME", "MIL"),
}


def normalize_market(raw: str, ticker: str) -> str:
    """'KASE' -> KZ, 'NYSE/NASDAQ' -> US, 'ITS (США)' -> US. Пусто -> угадываем по тикеру."""
    value = raw.strip().upper()
    if not value:
        return guess_market(ticker)
    if value in DEFAULT_CURRENCY:
        return value
    words = set(re.findall(r"[A-ZА-ЯЁ]+", value))
    for market, names in MARKET_ALIASES.items():
        if words & set(names):
            return market
    raise ValueError(f"неизвестный рынок {raw.strip()!r}: укажите US, EU или KZ (или биржу: NYSE, NASDAQ, KASE, AIX, XETRA, LSE)")


def guess_market(ticker: str) -> str:
    t = ticker.upper()
    if t.endswith(".KZ"):
        return "KZ"
    if t.endswith(EU_SUFFIXES):
        return "EU"
    return "US"


def _detect_delimiter(text: str) -> str:
    first = text.splitlines()[0] if text.splitlines() else ""
    counts = {d: first.count(d) for d in (",", ";", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def parse_csv(text: str) -> tuple[list[tuple[int, PositionCreate]], list[tuple[int, str]]]:
    """Возвращает (строки, ошибки); номера строк считаются как в файле (заголовок — строка 1)."""
    text = text.lstrip("﻿")
    if not text.strip():
        return [], [(1, "файл пустой")]

    reader = csv.reader(io.StringIO(text), delimiter=_detect_delimiter(text))
    rows = list(reader)
    mapping = _map_headers(rows[0])
    missing = [f for f in ("ticker", "quantity", "buy_price", "buy_date") if f not in mapping]
    if missing:
        names = {"ticker": "тикер", "quantity": "количество", "buy_price": "цена покупки", "buy_date": "дата"}
        return [], [(1, "не найдены колонки: " + ", ".join(names[m] for m in missing)
                     + ". Нужны: тикер, количество, цена покупки, дата в первой строке файла.")]

    parsed: list[tuple[int, PositionCreate]] = []
    errors: list[tuple[int, str]] = []

    def cell(row: list[str], field: str) -> str:
        i = mapping.get(field)
        return row[i].strip() if i is not None and i < len(row) else ""

    for line_no, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue  # пустая строка
        try:
            ticker = cell(row, "ticker").upper()
            if not ticker:
                raise ValueError("не указан тикер")
            market = normalize_market(cell(row, "market"), ticker)
            fee_raw = cell(row, "fee")
            position = PositionCreate(
                ticker=ticker,
                market=market,
                quantity=parse_number(cell(row, "quantity")),
                buy_price=parse_number(cell(row, "buy_price")),
                buy_date=parse_date(cell(row, "buy_date")),
                fee=parse_number(fee_raw) if fee_raw else 0.0,
                currency=cell(row, "currency") or DEFAULT_CURRENCY[market],
                note=cell(row, "note")[:500],
            )
            parsed.append((line_no, position))
        except ValidationError as exc:
            msgs = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            errors.append((line_no, msgs))
        except ValueError as exc:
            errors.append((line_no, str(exc)))
    return parsed, errors
