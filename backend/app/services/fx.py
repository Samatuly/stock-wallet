"""Курсы валют, чтобы показать стоимость портфеля в одной выбранной валюте.

Источник: Frankfurter (https://www.frankfurter.app) — бесплатный API без ключа,
собирает официальные курсы центробанков (включая курс тенге). Лимитов на запросы
нет, но мы всё равно кэшируем на сутки: курсы обновляются не чаще раза в день.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Optional

import httpx
from sqlalchemy.orm import Session

from app.models import FxRate, utcnow

log = logging.getLogger(__name__)

BASE = "USD"
# api.frankfurter.app переехал на api.frankfurter.dev (сентябрь 2026).
# Важно: используем /v2/, а не /v1/ — v1 это "замороженный" набор только на
# ~30 валют ЕЦБ и НЕ включает тенге (KZT). Тенге есть только в v2 (23 источника).
# Формат ответа v2 тоже другой: плоский список {date, base, quote, rate} —
# по одной строке на валюту, а не вложенный объект {"rates": {...}} как в v1.
URL = "https://api.frankfurter.dev/v2/rates"


@dataclass
class RateTable:
    rates: dict[str, float]  # курс USD -> валюта, например {"EUR": 0.92, "KZT": 470.5}
    as_of: Optional[date]
    is_stale: bool
    missing: list[str] = field(default_factory=list)  # запрошенные валюты без курса

    def convert(self, amount: float, from_ccy: str, to_ccy: str) -> Optional[float]:
        if from_ccy == to_ccy:
            return amount
        rate_from = self.rates.get(from_ccy)
        rate_to = self.rates.get(to_ccy)
        if not rate_from or rate_to is None:
            return None
        return amount / rate_from * rate_to  # через доллар как промежуточную валюту


class FxService:
    def __init__(
        self,
        db: Session,
        ttl_seconds: int = 86400,
        now: Callable[[], datetime] = utcnow,
        http_get: Callable = httpx.get,
    ):
        self.db = db
        self.ttl = timedelta(seconds=ttl_seconds)
        self.now = now
        self.http_get = http_get

    def get_rates(self, currencies: set[str]) -> RateTable:
        wanted = {c.upper() for c in currencies} | {BASE}
        cached = self.db.get(FxRate, BASE)
        cached_rates = cached.rates() if cached else {}
        is_fresh = bool(cached) and self.now() - cached.fetched_at < self.ttl

        if is_fresh and wanted <= set(cached_rates):
            return RateTable(cached_rates, cached.as_of, False, [])

        symbols = sorted(wanted - {BASE})
        if not symbols:
            # Нужен только доллар — курс не требуется, обращаться к источнику незачем.
            as_of = cached.as_of if cached else self.now().date()
            return RateTable({BASE: 1.0, **cached_rates}, as_of, False, [])
        try:
            resp = self.http_get(
                URL,
                params={"base": BASE, "quotes": ",".join(symbols)},
                timeout=8.0,
                follow_redirects=True,  # на случай, если источник опять переедет
            )
            resp.raise_for_status()
            rows = resp.json()  # [{"date": "...", "base": "USD", "quote": "EUR", "rate": 0.92}, ...]
            fresh = {BASE: 1.0}
            as_of = None
            for row in rows:
                if row.get("base", "").upper() != BASE:
                    continue  # источник иногда возвращает пары не от той базы — пропускаем
                fresh[row["quote"].upper()] = float(row["rate"])
                as_of = date.fromisoformat(row["date"])
            if as_of is None:
                raise ValueError("пустой или неожиданный ответ Frankfurter")
            merged = {**cached_rates, **fresh}
            self.db.merge(
                FxRate(base=BASE, rates_json=json.dumps(merged), as_of=as_of, fetched_at=self.now())
            )
            self.db.commit()
            return RateTable(merged, as_of, False, sorted(wanted - set(merged)))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("Не удалось получить курсы валют: %s", exc)
            if cached_rates:
                return RateTable(cached_rates, cached.as_of, True, sorted(wanted - set(cached_rates)))
            return RateTable({BASE: 1.0}, None, True, sorted(wanted - {BASE}))
