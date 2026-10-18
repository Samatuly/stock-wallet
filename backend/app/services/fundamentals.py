"""Базовые фундаментальные метрики: P/E, дивидендная доходность, дата отчёта.

Источник — yfinance (Ticker.get_info()), то же ограничение по времени, что и
у остальных обращений к Yahoo (см. app/services/_timeout.py), и та же защита
от NaN, которая однажды уже роняла дашборд на истории цены.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models import FundamentalsCache, utcnow
from app.services._timeout import run_with_timeout

log = logging.getLogger(__name__)


class FundamentalsProviderError(Exception):
    """Источник не смог вернуть фундаментальные данные."""


@dataclass
class Fundamentals:
    ticker: str
    pe_ratio: Optional[float]
    dividend_yield: Optional[float]  # в процентах, например 0.52 значит 0.52%
    next_earnings_date: Optional[date]
    currency: Optional[str]
    source: str
    fetched_at: datetime
    is_stale: bool = False


def _safe_float(value) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _dividend_yield_percent(info: dict) -> Optional[float]:
    """Дивидендная доходность в процентах.

    Основной путь — разделить годовой дивиденд в долларах (dividendRate) на
    текущую цену: это однозначно, формат доллара не бывает двусмысленным.

    Раньше здесь была эвристика "если dividendYield меньше 1 — это доля,
    умножаем на 100". Она оказалась неверной: для AAPL реальный yfinance
    вернул dividendYield уже в процентах (0.33 значит 0.33%), а эвристика
    превратила это в 33% — абсурдное значение для Apple, которое и выявило
    баг. Разные версии yfinance действительно отдают это поле по-разному,
    и надёжно отличить доли от процентов нельзя — поэтому теперь это поле
    используется только как запасной вариант и без домножения, а совсем
    неправдоподобные значения (больше 25%) отбрасываются как ошибка данных,
    а не показываются пользователю.
    """
    rate = _safe_float(info.get("dividendRate"))
    price = (
        _safe_float(info.get("currentPrice"))
        or _safe_float(info.get("regularMarketPrice"))
        or _safe_float(info.get("previousClose"))
    )
    if rate is not None and rate > 0 and price:
        return round(rate / price * 100, 4)

    raw = _safe_float(info.get("dividendYield"))
    if raw is not None and 0 < raw <= 25:
        return round(raw, 4)
    return None


def parse_fundamentals(info: dict, ticker: str, now: datetime) -> Fundamentals:
    """Разбирает сырой словарь от yfinance. Вынесено отдельно, чтобы тестировать
    без обращения к настоящему yfinance."""
    pe = _safe_float(info.get("trailingPE"))
    div_yield = _dividend_yield_percent(info)

    next_earnings = None
    ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
    if ts:
        try:
            next_earnings = datetime.fromtimestamp(ts).date()
        except (TypeError, ValueError, OSError, OverflowError):
            next_earnings = None

    return Fundamentals(
        ticker=ticker,
        pe_ratio=pe,
        dividend_yield=div_yield,
        next_earnings_date=next_earnings,
        currency=info.get("currency"),
        source="yfinance",
        fetched_at=now,
    )


class YahooFundamentalsProvider:
    name = "yfinance"

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def fetch(self, ticker: str) -> dict:
        def _call():
            import yfinance as yf

            return yf.Ticker(ticker).get_info()

        try:
            return run_with_timeout(_call, self.timeout_seconds)
        except Exception as exc:  # yfinance не имеет официального API, ошибки бывают разные
            raise FundamentalsProviderError(f"yfinance: {exc}") from exc


class FundamentalsService:
    def __init__(
        self,
        db: Session,
        provider,
        ttl_seconds: int = 86400,
        now: Callable[[], datetime] = utcnow,
    ):
        self.db = db
        self.provider = provider
        self.ttl = timedelta(seconds=ttl_seconds)
        self.now = now

    def _from_cache(self, cached: FundamentalsCache, is_stale: bool) -> Fundamentals:
        return Fundamentals(
            ticker=cached.ticker,
            pe_ratio=cached.pe_ratio,
            dividend_yield=cached.dividend_yield,
            next_earnings_date=cached.next_earnings_date,
            currency=cached.currency,
            source=cached.source,
            fetched_at=cached.fetched_at,
            is_stale=is_stale,
        )

    def get(self, ticker: str, force: bool = False) -> Fundamentals:
        ticker = ticker.upper()
        cached = self.db.get(FundamentalsCache, ticker)
        is_fresh = cached is not None and self.now() - cached.fetched_at < self.ttl

        if is_fresh and not force:
            return self._from_cache(cached, is_stale=False)

        try:
            info = self.provider.fetch(ticker)
            result = parse_fundamentals(info, ticker, self.now())
        except FundamentalsProviderError as exc:
            log.warning("Не удалось получить фундаментальные данные %s: %s", ticker, exc)
            if cached:
                return self._from_cache(cached, is_stale=True)
            return Fundamentals(
                ticker=ticker, pe_ratio=None, dividend_yield=None, next_earnings_date=None,
                currency=None, source="unavailable", fetched_at=self.now(), is_stale=True,
            )

        self.db.merge(
            FundamentalsCache(
                ticker=ticker,
                pe_ratio=result.pe_ratio,
                dividend_yield=result.dividend_yield,
                next_earnings_date=result.next_earnings_date,
                currency=result.currency,
                source=result.source,
                fetched_at=result.fetched_at,
            )
        )
        self.db.commit()
        return result
