from datetime import date

import pytest

from app.models import PriceHistory
from app.services.history import Candle, HistoryProviderError, HistoryService


class FakeHistoryProvider:
    def __init__(self, candles=None, fail=False):
        self.candles = candles or []
        self.fail = fail
        self.calls = 0

    def fetch(self, ticker, days):
        self.calls += 1
        if self.fail:
            raise HistoryProviderError("нет сети")
        return self.candles


def candle(d, close, o=None, h=None, low=None, v=100):
    o = o if o is not None else close
    h = h if h is not None else close
    low = low if low is not None else close
    return Candle(date=d, open=o, high=h, low=low, close=close, volume=v)


def test_fetches_and_stores_history(db, clock):
    provider = FakeHistoryProvider([candle(date(2026, 9, 26), 190), candle(date(2026, 9, 27), 195)])
    svc = HistoryService(db, provider, now=clock)
    rows = svc.get_history("AAPL", days=30)
    assert [r.close for r in rows] == [190, 195]
    assert db.get(PriceHistory, ("AAPL", date(2026, 9, 27))) is not None


def test_cache_used_within_ttl(db, clock):
    provider = FakeHistoryProvider([candle(date(2026, 9, 27), 195)])
    svc = HistoryService(db, provider, now=clock, ttl_seconds=86400)
    svc.get_history("AAPL")
    clock.advance(3600)
    svc.get_history("AAPL")
    assert provider.calls == 1


def test_stale_cache_triggers_refetch(db, clock):
    provider = FakeHistoryProvider([candle(date(2026, 9, 27), 195)])
    svc = HistoryService(db, provider, now=clock, ttl_seconds=86400)
    svc.get_history("AAPL")
    clock.advance(100_000)
    provider.candles = [candle(date(2026, 9, 27), 195), candle(date(2026, 9, 28), 200)]
    rows = svc.get_history("AAPL")
    assert provider.calls == 2
    assert [r.close for r in rows] == [195, 200]


def test_force_refresh_ignores_fresh_cache(db, clock):
    provider = FakeHistoryProvider([candle(date(2026, 9, 27), 195)])
    svc = HistoryService(db, provider, now=clock)
    svc.get_history("AAPL")
    svc.get_history("AAPL", force=True)
    assert provider.calls == 2


def test_falls_back_to_cache_when_source_fails(db, clock):
    provider = FakeHistoryProvider([candle(date(2026, 9, 27), 195)])
    svc = HistoryService(db, provider, now=clock)
    svc.get_history("AAPL")
    clock.advance(100_000)
    provider.fail = True
    rows = svc.get_history("AAPL")
    assert [r.close for r in rows] == [195]  # старые данные не потеряны


def test_no_cache_and_source_fails_returns_empty(db, clock):
    provider = FakeHistoryProvider(fail=True)
    svc = HistoryService(db, provider, now=clock)
    assert svc.get_history("AAPL") == []


def test_days_window_filters_old_points(db, clock):
    provider = FakeHistoryProvider([candle(date(2025, 1, 1), 100), candle(date(2026, 9, 27), 195)])
    svc = HistoryService(db, provider, now=clock)
    rows = svc.get_history("AAPL", days=30)
    assert [r.close for r in rows] == [195]
