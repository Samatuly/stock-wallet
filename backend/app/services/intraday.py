"""Внутридневные цены (шаг 5 минут) для графика «1 день».

В базу не пишутся: данные быстро устаревают и нужны только для просмотра.
Держим их в памяти процесса на несколько минут, чтобы не дёргать источник
при каждом переключении периода.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Callable, Protocol

from app.models import utcnow
from app.services._timeout import run_with_timeout

log = logging.getLogger(__name__)


class IntradayProviderError(Exception):
    """Источник не смог вернуть внутридневные цены."""


@dataclass
class IntradayPoint:
    time: datetime  # время биржи, без часового пояса
    price: float


class IntradayProvider(Protocol):
    def fetch(self, ticker: str) -> list[IntradayPoint]: ...


class YahooIntradayProvider:
    name = "yfinance"

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def fetch(self, ticker: str) -> list[IntradayPoint]:
        def _call():
            import yfinance as yf

            # 5 дней, а не 1: в выходные и праздники за «сегодня» данных нет,
            # а показать последний торговый день всё равно нужно.
            return yf.Ticker(ticker).history(period="5d", interval="5m", timeout=self.timeout_seconds)

        try:
            hist = run_with_timeout(_call, self.timeout_seconds)
        except Exception as exc:  # TimeoutError и любые ошибки yfinance
            raise IntradayProviderError(f"yfinance: {exc}") from exc

        if hist is None or hist.empty:
            raise IntradayProviderError("нет внутридневных данных")

        points = []
        for idx, row in hist.iterrows():
            try:
                price = float(row["Close"])
            except (TypeError, ValueError, KeyError):
                continue
            if math.isnan(price):
                continue
            ts = idx.to_pydatetime().replace(tzinfo=None)
            points.append(IntradayPoint(time=ts, price=price))
        if not points:
            raise IntradayProviderError("не удалось разобрать внутридневные данные")
        return points


def last_session(points: list[IntradayPoint]) -> list[IntradayPoint]:
    """Оставляет только последний торговый день."""
    if not points:
        return []
    last_day = max(p.time.date() for p in points)
    return sorted((p for p in points if p.time.date() == last_day), key=lambda p: p.time)


class IntradayService:
    _cache: dict[str, tuple[datetime, list[IntradayPoint]]] = {}
    _lock = Lock()

    def __init__(
        self,
        provider: IntradayProvider,
        ttl_seconds: int = 300,
        now: Callable[[], datetime] = utcnow,
        cache: dict | None = None,
    ):
        self.provider = provider
        self.ttl = timedelta(seconds=ttl_seconds)
        self.now = now
        self.cache = IntradayService._cache if cache is None else cache

    def get(self, ticker: str) -> list[IntradayPoint]:
        ticker = ticker.upper()
        with self._lock:
            hit = self.cache.get(ticker)
        if hit and self.now() - hit[0] < self.ttl:
            return hit[1]

        try:
            points = last_session(self.provider.fetch(ticker))
        except IntradayProviderError as exc:
            log.warning("Нет внутридневных цен %s: %s", ticker, exc)
            return hit[1] if hit else []  # старые точки лучше пустого графика

        with self._lock:
            self.cache[ticker] = (self.now(), points)
        return points
