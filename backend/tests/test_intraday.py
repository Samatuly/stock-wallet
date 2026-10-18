from datetime import datetime

from app.deps import get_intraday_service
from app.main import app
from app.services.intraday import IntradayPoint, IntradayProviderError, IntradayService, last_session


def pts(*items):
    return [IntradayPoint(time=datetime.fromisoformat(t), price=p) for t, p in items]


class FakeProvider:
    def __init__(self, points=None, fail=False):
        self.points = points or []
        self.fail = fail
        self.calls = 0

    def fetch(self, ticker):
        self.calls += 1
        if self.fail:
            raise IntradayProviderError("нет данных")
        return self.points


def test_last_session_keeps_only_latest_day_sorted():
    data = pts(("2026-10-15 15:55", 99.0), ("2026-10-16 09:35", 101.0), ("2026-10-16 09:30", 100.0))
    out = last_session(data)
    assert [p.price for p in out] == [100.0, 101.0]


def test_last_session_empty():
    assert last_session([]) == []


def test_cache_within_ttl(clock):
    provider = FakeProvider(pts(("2026-10-16 09:30", 100.0)))
    service = IntradayService(provider, ttl_seconds=300, now=clock, cache={})
    service.get("aapl")
    service.get("AAPL")
    assert provider.calls == 1
    clock.advance(301)
    service.get("AAPL")
    assert provider.calls == 2


def test_failure_returns_stale_points(clock):
    cache = {}
    ok = IntradayService(FakeProvider(pts(("2026-10-16 09:30", 100.0))), ttl_seconds=1, now=clock, cache=cache)
    assert len(ok.get("AAPL")) == 1
    clock.advance(5)
    broken = IntradayService(FakeProvider(fail=True), ttl_seconds=1, now=clock, cache=cache)
    assert [p.price for p in broken.get("AAPL")] == [100.0]


def test_failure_without_cache_is_empty(clock):
    service = IntradayService(FakeProvider(fail=True), now=clock, cache={})
    assert service.get("AAPL") == []


def test_intraday_endpoint(client, clock):
    provider = FakeProvider(pts(("2026-10-16 09:30", 100.12341), ("2026-10-16 09:35", 101.0)))
    app.dependency_overrides[get_intraday_service] = lambda: IntradayService(provider, now=clock, cache={})
    try:
        r = client.get("/quotes/aapl/intraday")
    finally:
        app.dependency_overrides.pop(get_intraday_service, None)
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert [p["price"] for p in body["points"]] == [100.1234, 101.0]
