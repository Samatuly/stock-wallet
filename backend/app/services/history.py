"""История дневных цен для графика. Источник — yfinance (как для Европы и Казахстана).

Последний загруженный день кэшируется на сутки: график за год не перекачивается
заново при каждом открытии карточки, только когда кэш устарел.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date as date_
from datetime import datetime, timedelta
from typing import Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PriceHistory, utcnow
from app.services._timeout import run_with_timeout

log = logging.getLogger(__name__)


class HistoryProviderError(Exception):
    """Источник не смог вернуть историю цены."""


@dataclass
class Candle:
    date: date_
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class HistoryProvider(Protocol):
    def fetch(self, ticker: str, days: int) -> list[Candle]: ...


class YahooHistoryProvider:
    name = "yfinance"

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def fetch(self, ticker: str, days: int) -> list[Candle]:
        period = "1mo" if days <= 30 else "1y" if days <= 365 else "2y" if days <= 730 else "5y"

        def _call():
            import yfinance as yf

            return yf.Ticker(ticker).history(period=period, interval="1d", timeout=self.timeout_seconds)

        try:
            hist = run_with_timeout(_call, self.timeout_seconds)
        except TimeoutError as exc:
            raise HistoryProviderError(f"yfinance: {exc}") from exc
        except Exception as exc:  # yfinance не имеет официального API, ошибки бывают разные
            raise HistoryProviderError(f"yfinance: {exc}") from exc

        if hist is None or hist.empty:
            raise HistoryProviderError("нет исторических данных")

        candles = parse_history_dataframe(hist)
        if not candles:
            raise HistoryProviderError("не удалось разобрать историю")
        return candles


def parse_history_dataframe(hist) -> list[Candle]:
    """Превращает DataFrame от yfinance в список свечей.

    Вынесено в отдельную функцию, чтобы тестировать разбор без обращения
    к настоящему yfinance — достаточно собрать маленький DataFrame руками.

    Важно: строки с NaN в цене отбрасываются явно через math.isnan(), а не
    полагаясь на то, что float() или except их отловит — float(nan) НЕ бросает
    исключение. Yahoo Finance отдаёт NaN для сегодняшнего ещё не закрытого
    торгового дня (объём при этом может быть указан, а цены ещё нет). Если
    такую строку не отфильтровать, при записи в SQLite она вызовет
    IntegrityError: Python-драйвер sqlite3 интерпретирует NaN как NULL, а
    колонки цены помечены NOT NULL.
    """
    candles = []
    for idx, row in hist.iterrows():
        try:
            o, h, l, c = (float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]))
            v = float(row.get("Volume", 0) or 0)
        except (TypeError, ValueError, KeyError):
            continue  # пропускаем битую строку, а не всю историю
        if any(math.isnan(x) for x in (o, h, l, c)):
            continue  # сегодняшний день ещё не закрылся — цены ещё нет
        candles.append(Candle(date=idx.date(), open=o, high=h, low=l, close=c, volume=v))
    return candles


class HistoryService:
    def __init__(
        self,
        db: Session,
        provider: HistoryProvider,
        ttl_seconds: int = 86400,
        now: Callable[[], datetime] = utcnow,
    ):
        self.db = db
        self.provider = provider
        self.ttl = timedelta(seconds=ttl_seconds)
        self.now = now

    def _cached(self, ticker: str, days: int) -> list[PriceHistory]:
        since = self.now().date() - timedelta(days=days)
        rows = self.db.scalars(
            select(PriceHistory)
            .where(PriceHistory.ticker == ticker, PriceHistory.date >= since)
            .order_by(PriceHistory.date)
        ).all()
        return list(rows)

    def get_history(self, ticker: str, days: int = 365, force: bool = False) -> list[PriceHistory]:
        ticker = ticker.upper()
        cached = self._cached(ticker, days)
        latest = cached[-1] if cached else None
        is_fresh = latest is not None and self.now() - latest.fetched_at < self.ttl

        if is_fresh and not force:
            return cached

        try:
            candles = self.provider.fetch(ticker, days)
        except HistoryProviderError as exc:
            log.warning("Не удалось получить историю %s: %s", ticker, exc)
            return cached  # старые данные лучше, чем пустой график

        fetched_at = self.now()
        for c in candles:
            # Вторая линия защиты: даже если когда-нибудь появится другой провайдер
            # (не только yfinance) и вернёт NaN, не даём ему уронить запись в базу —
            # SQLite превращает NaN в NULL, а колонки цены помечены NOT NULL.
            if any(math.isnan(x) for x in (c.open, c.high, c.low, c.close)):
                continue
            self.db.merge(
                PriceHistory(
                    ticker=ticker,
                    date=c.date,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                    fetched_at=fetched_at,
                )
            )
        self.db.commit()
        return self._cached(ticker, days)
