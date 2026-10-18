"""Получение текущих цен.

Порядок источников:
  США:            кэш -> Finnhub -> yfinance -> ручная цена -> устаревший кэш
  Европа, Казахстан: кэш -> yfinance -> ручная цена -> устаревший кэш
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol

import httpx
from sqlalchemy.orm import Session

from app.models import ManualPrice, PriceCache, utcnow
from app.services._timeout import run_with_timeout

log = logging.getLogger(__name__)


class QuoteProviderError(Exception):
    """Источник не смог вернуть цену."""


@dataclass
class Quote:
    ticker: str
    price: float
    currency: Optional[str]
    source: str  # finnhub, yfinance, manual, cache-stale
    fetched_at: datetime
    is_manual: bool = False


class Provider(Protocol):
    name: str

    def fetch(self, ticker: str) -> tuple[float, Optional[str]]:
        """Вернуть (цена, валюта) или бросить QuoteProviderError."""
        ...


def _valid_price(value) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError):
        raise QuoteProviderError("цена не число")
    if math.isnan(price) or price <= 0:
        raise QuoteProviderError("нет цены")
    return price


class FinnhubProvider:
    name = "finnhub"
    URL = "https://finnhub.io/api/v1/quote"

    def __init__(self, api_key: str, timeout: float = 8.0):
        self.api_key = api_key
        self.timeout = timeout

    def fetch(self, ticker: str) -> tuple[float, Optional[str]]:
        if not self.api_key:
            raise QuoteProviderError("FINNHUB_API_KEY не задан")
        try:
            resp = httpx.get(
                self.URL,
                params={"symbol": ticker, "token": self.api_key},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise QuoteProviderError(f"Finnhub: {exc}") from exc
        # Finnhub возвращает c=0 для неизвестных тикеров. Валюту не отдаёт: для США это USD.
        return _valid_price(data.get("c")), "USD"


class YahooProvider:
    name = "yfinance"

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def fetch(self, ticker: str) -> tuple[float, Optional[str]]:
        def _call():
            import yfinance as yf

            info = yf.Ticker(ticker).fast_info
            return _valid_price(info.last_price), getattr(info, "currency", None)

        try:
            return run_with_timeout(_call, self.timeout_seconds)
        except QuoteProviderError:
            raise
        except TimeoutError as exc:
            raise QuoteProviderError(f"yfinance: {exc}") from exc
        except Exception as exc:  # yfinance не имеет официального API и часто меняется
            raise QuoteProviderError(f"yfinance: {exc}") from exc


class QuoteService:
    def __init__(
        self,
        db: Session,
        finnhub: Provider,
        yahoo: Provider,
        ttl_seconds: int = 300,
        now: Callable[[], datetime] = utcnow,
    ):
        self.db = db
        self.finnhub = finnhub
        self.yahoo = yahoo
        self.ttl = timedelta(seconds=ttl_seconds)
        self.now = now

    def _chain(self, market: str) -> list[Provider]:
        return [self.finnhub, self.yahoo] if market == "US" else [self.yahoo]

    def get_quote(self, ticker: str, market: str = "US", force: bool = False) -> Optional[Quote]:
        ticker = ticker.upper()
        cached = self.db.get(PriceCache, ticker)

        if cached and not force and self.now() - cached.fetched_at < self.ttl:
            return Quote(ticker, cached.price, cached.currency, cached.source, cached.fetched_at)

        for provider in self._chain(market):
            try:
                price, currency = provider.fetch(ticker)
            except QuoteProviderError as exc:
                log.warning("Не удалось получить %s из %s: %s", ticker, provider.name, exc)
                continue
            fetched_at = self.now()
            self.db.merge(
                PriceCache(
                    ticker=ticker,
                    price=price,
                    currency=currency,
                    source=provider.name,
                    fetched_at=fetched_at,
                )
            )
            self.db.commit()
            return Quote(ticker, price, currency, provider.name, fetched_at)

        manual = self.db.get(ManualPrice, ticker)
        if manual:
            return Quote(ticker, manual.price, manual.currency, "manual", manual.updated_at, True)

        if cached:  # лучше устаревшая цена с пометкой, чем пустое место
            return Quote(ticker, cached.price, cached.currency, "cache-stale", cached.fetched_at)
        return None

    def get_quotes(self, items: list[tuple[str, str]], force: bool = False) -> dict[str, Optional[Quote]]:
        """items: список (тикер, рынок). Каждый тикер запрашивается один раз."""
        result: dict[str, Optional[Quote]] = {}
        for ticker, market in items:
            key = ticker.upper()
            if key not in result:
                result[key] = self.get_quote(key, market, force)
        return result
