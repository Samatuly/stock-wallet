from datetime import date, datetime

import pytest

from app.models import FundamentalsCache
from app.services.fundamentals import (
    FundamentalsProviderError,
    FundamentalsService,
    parse_fundamentals,
)


class FakeProvider:
    def __init__(self, info=None, fail=False):
        self.info = info or {}
        self.fail = fail
        self.calls = 0

    def fetch(self, ticker):
        self.calls += 1
        if self.fail:
            raise FundamentalsProviderError("нет сети")
        return self.info


def test_parse_computes_dividend_yield_from_dollar_rate_and_price():
    # Основной, однозначный путь: $1 дивиденда при цене $200 -> ровно 0.5%
    f = parse_fundamentals(
        {"trailingPE": 28.5, "dividendRate": 1.0, "currentPrice": 200.0, "currency": "USD"},
        "AAPL", datetime(2026, 9, 30),
    )
    assert f.pe_ratio == 28.5
    assert f.dividend_yield == pytest.approx(0.5)


def test_regression_does_not_misread_already_percent_dividend_yield_as_fraction():
    """Баг, найденный на реальных данных: для AAPL (доходность ~0.3%) yfinance
    вернул dividendYield уже в процентах (0.33), а старая эвристика "если < 1,
    значит доля" домножала на 100, превращая 0.33% в абсурдные 33%."""
    f = parse_fundamentals({"dividendYield": 0.33}, "AAPL", datetime(2026, 9, 30))
    assert f.dividend_yield == pytest.approx(0.33)
    assert f.dividend_yield < 1  # ни в коем случае не 33


def test_parse_dividend_rate_takes_priority_over_dividend_yield_field():
    f = parse_fundamentals(
        {"dividendRate": 1.0, "currentPrice": 200.0, "dividendYield": 999},  # заведомо неверное поле
        "AAPL", datetime(2026, 9, 30),
    )
    assert f.dividend_yield == pytest.approx(0.5)


def test_parse_discards_implausible_dividend_yield_as_bad_data():
    # Больше 25% для обычной акции — явно ошибка формата, а не реальная доходность
    f = parse_fundamentals({"dividendYield": 33.0}, "WEIRD", datetime(2026, 9, 30))
    assert f.dividend_yield is None


def test_parse_drops_nan_values():
    f = parse_fundamentals({"trailingPE": float("nan")}, "XYZ", datetime(2026, 9, 30))
    assert f.pe_ratio is None


def test_parse_extracts_earnings_date_from_timestamp():
    ts = datetime(2026, 11, 1).timestamp()
    f = parse_fundamentals({"earningsTimestamp": ts}, "AAPL", datetime(2026, 9, 30))
    assert f.next_earnings_date == date(2026, 11, 1)


def test_parse_missing_fields_are_none_not_crash():
    f = parse_fundamentals({}, "NEW", datetime(2026, 9, 30))
    assert f.pe_ratio is None and f.dividend_yield is None and f.next_earnings_date is None


def test_service_fetches_and_caches(db, clock):
    provider = FakeProvider({"trailingPE": 25.0, "currency": "USD"})
    svc = FundamentalsService(db, provider, now=clock)
    result = svc.get("AAPL")
    assert result.pe_ratio == 25.0 and not result.is_stale
    assert db.get(FundamentalsCache, "AAPL") is not None


def test_service_uses_cache_within_ttl(db, clock):
    provider = FakeProvider({"trailingPE": 25.0})
    svc = FundamentalsService(db, provider, now=clock, ttl_seconds=86400)
    svc.get("AAPL")
    clock.advance(3600)
    svc.get("AAPL")
    assert provider.calls == 1


def test_service_falls_back_to_stale_cache_on_failure(db, clock):
    provider = FakeProvider({"trailingPE": 25.0})
    svc = FundamentalsService(db, provider, now=clock)
    svc.get("AAPL")
    clock.advance(100_000)
    provider.fail = True
    result = svc.get("AAPL")
    assert result.is_stale and result.pe_ratio == 25.0


def test_service_no_cache_and_failure_returns_empty_but_marked_stale(db, clock):
    svc = FundamentalsService(db, FakeProvider(fail=True), now=clock)
    result = svc.get("NEWCO")
    assert result.is_stale
    assert result.pe_ratio is None and result.source == "unavailable"
