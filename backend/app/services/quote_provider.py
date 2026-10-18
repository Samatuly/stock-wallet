"""Получение текущих цен.

Порядок источников:
  США:        кэш -> Finnhub -> yfinance -> ручная цена -> устаревший кэш
  Европа:     кэш -> yfinance -> ручная цена -> устаревший кэш
  Казахстан:  кэш -> Tradernet (Freedom, если заданы ключи) -> yfinance -> ручная цена -> устаревший кэш
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol

import hashlib
import hmac
import json
import time

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


class TradernetProvider:
    """Котировки через API Freedom Broker (Tradernet), в том числе бумаги KASE.

    Подпись запроса повторяет официальный tradernet-sdk (API v3):
    тело — JSON без пробелов, подпись — HMAC-SHA256(приватный ключ, тело + timestamp).
    """

    name = "tradernet"

    def __init__(self, public_key: str, private_key: str, domain: str = "freedom24.com", timeout: float = 8.0, http_post=None):
        self.public_key = public_key
        self.private_key = private_key
        self.domain = domain
        self.timeout = timeout
        self.http_post = http_post or httpx.post

    @property
    def enabled(self) -> bool:
        return bool(self.public_key and self.private_key)

    @staticmethod
    def symbol_for(ticker: str) -> str:
        """HSBK -> HSBK.KZ; уже с биржей (PYPL_KZ.KZ, AAPL.US) — без изменений."""
        t = ticker.upper()
        return t if "." in t else f"{t}.KZ"

    @staticmethod
    def sign(private_key: str, message: str) -> str:
        return hmac.new(private_key.encode(), message.encode(), hashlib.sha256).hexdigest()

    def request(self, cmd: str, params: dict) -> dict:
        payload = json.dumps(params, separators=(",", ":"))
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "stock-wallet/1.0 (+https://github.com/Samatuly/stock-wallet)",
            "X-NtApi-PublicKey": self.public_key,
            "X-NtApi-Timestamp": timestamp,
            "X-NtApi-Sig": self.sign(self.private_key, payload + timestamp),
        }
        resp = self.http_post(f"https://{self.domain}/api/{cmd}", headers=headers, content=payload, timeout=self.timeout)
        status = getattr(resp, "status_code", 200)
        if status >= 400:
            # Сервер часто объясняет причину в теле ответа (неверная подпись, нет доступа) — показываем её
            body = (getattr(resp, "text", "") or "")[:300].strip()
            raise QuoteProviderError(f"Tradernet HTTP {status}: {body or 'без описания'}")
        return resp.json()

    def fetch(self, ticker: str) -> tuple[float, Optional[str]]:
        if not self.enabled:
            raise QuoteProviderError("ключи Tradernet не заданы")
        symbol = self.symbol_for(ticker)
        try:
            data = self.request("getStockQuotesJson", {"tickers": symbol})
        except QuoteProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise QuoteProviderError(f"Tradernet: {exc}") from exc
        return parse_tradernet_quote(data, symbol)


_PRICE_KEYS = ("ltp", "lp", "last", "close", "pp")
_CURRENCY_KEYS = ("x_curr", "curr", "currency")


def parse_tradernet_quote(data, symbol: str) -> tuple[float, Optional[str]]:
    """Ищет в ответе котировку нужного тикера. Формат ответа описан не везде одинаково,
    поэтому разбираем защитно: любой вложенный объект с полем c == тикер."""
    if isinstance(data, dict):
        err = data.get("errMsg") or data.get("error")
        if err:
            raise QuoteProviderError(f"Tradernet: {err}")

    stack, found = [data], None
    while stack and found is None:
        node = stack.pop()
        if isinstance(node, dict):
            if str(node.get("c", "")).upper() == symbol.upper():
                found = node
                break
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    if found is None:
        raise QuoteProviderError(f"Tradernet: нет котировки {symbol}")

    for key in _PRICE_KEYS:
        if found.get(key) not in (None, "", 0, "0"):
            currency = next((str(found[k]).upper() for k in _CURRENCY_KEYS if found.get(k)), None)
            return _valid_price(found[key]), currency
    raise QuoteProviderError(f"Tradernet: нет цены для {symbol}")


class QuoteService:
    def __init__(
        self,
        db: Session,
        finnhub: Provider,
        yahoo: Provider,
        ttl_seconds: int = 300,
        now: Callable[[], datetime] = utcnow,
        tradernet: Optional[Provider] = None,
    ):
        self.db = db
        self.finnhub = finnhub
        self.yahoo = yahoo
        self.tradernet = tradernet
        self.ttl = timedelta(seconds=ttl_seconds)
        self.now = now

    def _chain(self, market: str) -> list[Provider]:
        if market == "US":
            return [self.finnhub, self.yahoo]
        if market == "KZ" and self.tradernet is not None and getattr(self.tradernet, "enabled", True):
            return [self.tradernet, self.yahoo]
        return [self.yahoo]

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
