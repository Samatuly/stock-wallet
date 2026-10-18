from datetime import date

import httpx
import pytest

from app.models import FxRate
from app.services.fx import FxService, RateTable


class FakeResponse:
    """Имитирует ответ Frankfurter v2: плоский список {date, base, quote, rate}."""

    def __init__(self, rows=None, status=200):
        self._rows = rows or []
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)

    def json(self):
        return self._rows


def v2_rows(rates: dict[str, float], as_of="2026-09-28", base="USD"):
    """Собирает строки в формате v2 из простого словаря {валюта: курс}."""
    return [{"date": as_of, "base": base, "quote": q, "rate": r} for q, r in rates.items()]


def frankfurter_ok(rates, as_of="2026-09-28"):
    def _get(url, params=None, timeout=None, follow_redirects=False):
        requested = set(params["quotes"].split(","))
        return FakeResponse(v2_rows({k: v for k, v in rates.items() if k in requested}, as_of))

    return _get


def frankfurter_down(*a, **k):
    raise httpx.ConnectError("нет сети")


def test_fetches_and_caches_rates(db, clock):
    fx = FxService(db, http_get=frankfurter_ok({"EUR": 0.92, "KZT": 470.5}), now=clock)
    table = fx.get_rates({"EUR", "KZT"})
    assert table.rates == {"USD": 1.0, "EUR": 0.92, "KZT": 470.5}
    assert table.as_of == date(2026, 9, 28)
    assert not table.is_stale and table.missing == []
    assert db.get(FxRate, "USD") is not None


def test_kzt_is_supported_end_to_end(db, clock):
    """Регрессия: v1 Frankfurter не знал тенге вообще. v2 знает — проверяем явно."""
    fx = FxService(db, http_get=frankfurter_ok({"KZT": 470.5}), now=clock)
    table = fx.get_rates({"KZT"})
    assert table.rates["KZT"] == 470.5
    assert table.missing == []


def test_cache_is_used_within_ttl(db, clock):
    calls = []

    def counting_get(url, params=None, timeout=None, follow_redirects=False):
        calls.append(1)
        return FakeResponse(v2_rows({"EUR": 0.92}))

    fx = FxService(db, http_get=counting_get, now=clock, ttl_seconds=86400)
    fx.get_rates({"EUR"})
    clock.advance(3600)
    fx.get_rates({"EUR"})  # тот же набор валют, должен взять из кэша
    assert len(calls) == 1


def test_new_currency_triggers_refetch_even_within_ttl(db, clock):
    calls = []
    all_rates = {"EUR": 0.92, "KZT": 470.5}

    def counting_get(url, params=None, timeout=None, follow_redirects=False):
        calls.append(params["quotes"])
        requested = params["quotes"].split(",")
        return FakeResponse(v2_rows({k: all_rates[k] for k in requested}))

    fx = FxService(db, http_get=counting_get, now=clock)
    fx.get_rates({"EUR"})
    fx.get_rates({"EUR", "KZT"})  # KZT ещё не был закэширован
    assert len(calls) == 2


def test_falls_back_to_stale_cache_when_source_down(db, clock):
    fx = FxService(db, http_get=frankfurter_ok({"EUR": 0.92}), now=clock)
    fx.get_rates({"EUR"})
    clock.advance(100_000)
    fx = FxService(db, http_get=frankfurter_down, now=clock)
    table = fx.get_rates({"EUR"})
    assert table.is_stale and table.rates["EUR"] == 0.92


def test_no_cache_and_source_down_returns_usd_only(db, clock):
    fx = FxService(db, http_get=frankfurter_down, now=clock)
    table = fx.get_rates({"EUR", "KZT"})
    assert table.rates == {"USD": 1.0}
    assert table.is_stale
    assert set(table.missing) == {"EUR", "KZT"}


def test_ignores_rows_with_wrong_base_and_falls_back(db, clock):
    """Если источник вдруг вернул пары не от USD (как это уже случалось), не должны
    молча посчитать неверный курс — лучше явная ошибка и отказ от устаревших данных."""

    def wrong_base_get(url, params=None, timeout=None, follow_redirects=False):
        return FakeResponse(v2_rows({"USD": 1.1748, "KZT": 592.25}, base="EUR"))

    fx = FxService(db, http_get=wrong_base_get, now=clock)
    table = fx.get_rates({"KZT"})
    assert table.is_stale
    assert "KZT" in table.missing


def test_empty_response_falls_back_to_stale_cache(db, clock):
    fx = FxService(db, http_get=frankfurter_ok({"EUR": 0.92}), now=clock)
    fx.get_rates({"EUR"})
    clock.advance(100_000)

    def empty_get(url, params=None, timeout=None, follow_redirects=False):
        return FakeResponse([])

    fx2 = FxService(db, http_get=empty_get, now=clock)
    table = fx2.get_rates({"EUR"})
    assert table.is_stale and table.rates["EUR"] == 0.92


@pytest.mark.parametrize(
    "amount,frm,to,expected",
    [(100, "USD", "USD", 100), (92, "EUR", "USD", 100), (100, "USD", "EUR", 92)],
)
def test_convert(amount, frm, to, expected):
    table = RateTable(rates={"USD": 1.0, "EUR": 0.92}, as_of=date(2026, 9, 28), is_stale=False)
    assert table.convert(amount, frm, to) == pytest.approx(expected, rel=1e-6)


def test_convert_returns_none_for_unknown_currency():
    table = RateTable(rates={"USD": 1.0}, as_of=None, is_stale=False)
    assert table.convert(100, "USD", "KZT") is None


def test_no_extra_currencies_needed_skips_network_call(db, clock):
    calls = []

    def should_not_be_called(*a, **k):
        calls.append(1)
        raise AssertionError("не должен обращаться к источнику, если нужен только USD")

    fx = FxService(db, http_get=should_not_be_called, now=clock)
    table = fx.get_rates({"USD"})
    assert table.rates == {"USD": 1.0}
    assert not table.is_stale and table.missing == []
    assert calls == []


def test_follows_redirects_and_uses_v2_domain(db, clock):
    """Регрессия: api.frankfurter.app переехал на api.frankfurter.dev/v2 (v1 не знает
    тенге и отвечает редиректом 301, который httpx по умолчанию не проходит)."""
    seen = {}

    def spy_get(url, params=None, timeout=None, follow_redirects=False):
        seen["url"] = url
        seen["follow_redirects"] = follow_redirects
        assert "frankfurter.dev/v2" in url
        return FakeResponse(v2_rows({"EUR": 0.92}))

    fx = FxService(db, http_get=spy_get, now=clock)
    fx.get_rates({"EUR"})
    assert seen["follow_redirects"] is True
