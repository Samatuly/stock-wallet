import math
from datetime import date

from app.models import Position, PriceHistory
from app.services.dashboard import annualized_volatility, build_dashboard
from app.services.fx import RateTable
from app.services.quote_provider import Quote

NOW = None  # используется только через Quote.fetched_at, время неважно для этого теста


def pos(id, ticker, qty, buy, currency="USD", market="US", buy_date_="2026-01-15"):
    return Position(
        id=id, ticker=ticker, market=market, quantity=qty, buy_price=buy,
        buy_date=date.fromisoformat(buy_date_), fee=0.0, currency=currency, note="",
    )


def quote(ticker, price, currency="USD", source="finnhub"):
    return Quote(ticker, price, currency, source, date(2026, 9, 30))


def history(ticker, closes, start=date(2026, 1, 1)):
    from datetime import timedelta
    return [
        PriceHistory(ticker=ticker, date=start + timedelta(days=i), open=c, high=c, low=c,
                     close=c, volume=100, fetched_at=None)
        for i, c in enumerate(closes)
    ]


RATE_USD_ONLY = RateTable(rates={"USD": 1.0}, as_of=date(2026, 9, 30), is_stale=False)


def test_allocation_sums_to_hundred_percent():
    positions = [pos(1, "AAPL", 10, 100), pos(2, "MSFT", 5, 200)]
    quotes = {"AAPL": quote("AAPL", 150), "MSFT": quote("MSFT", 300)}
    result = build_dashboard(positions, quotes, RATE_USD_ONLY, "USD", {})
    total_percent = sum(a.percent for a in result.allocation_by_ticker)
    assert math.isclose(total_percent, 100.0, abs_tol=0.1)
    # AAPL: 1500, MSFT: 1500 -> по 50%
    by_ticker = {a.label: a.percent for a in result.allocation_by_ticker}
    assert by_ticker["AAPL"] == 50.0 and by_ticker["MSFT"] == 50.0


def test_allocation_by_market_and_currency():
    positions = [
        pos(1, "AAPL", 10, 100, currency="USD", market="US"),
        pos(2, "SAP.DE", 10, 100, currency="EUR", market="EU"),
    ]
    quotes = {"AAPL": quote("AAPL", 100), "SAP.DE": quote("SAP.DE", 100, currency="EUR")}
    result = build_dashboard(positions, quotes, RATE_USD_ONLY, "USD", {})
    # без курса EUR->USD (RATE_USD_ONLY не знает EUR) EUR-позиция должна быть исключена
    assert result.missing_currencies == ["EUR"]
    by_market = {a.label: a.value for a in result.allocation_by_market}
    assert "EU" not in by_market and by_market["US"] == 1000.0


def test_top_and_bottom_positions_no_duplicates_when_few():
    positions = [pos(1, "A", 1, 100), pos(2, "B", 1, 100), pos(3, "C", 1, 100)]
    quotes = {"A": quote("A", 150), "B": quote("B", 100), "C": quote("C", 50)}
    result = build_dashboard(positions, quotes, RATE_USD_ONLY, "USD", {})
    top_tickers = {p.ticker for p in result.top_positions}
    bottom_tickers = {p.ticker for p in result.bottom_positions}
    assert top_tickers == {"A", "B", "C"}  # все 3 в топе, раз их мало
    assert bottom_tickers == set()  # антитоп пуст, чтобы не дублировать


def test_top_and_bottom_do_not_overlap_with_many_positions():
    positions = [pos(i, f"T{i}", 1, 100) for i in range(12)]
    quotes = {f"T{i}": quote(f"T{i}", 100 + i) for i in range(12)}  # T11 лучший, T0 худший
    result = build_dashboard(positions, quotes, RATE_USD_ONLY, "USD", {})
    top_tickers = {p.ticker for p in result.top_positions}
    bottom_tickers = {p.ticker for p in result.bottom_positions}
    assert top_tickers.isdisjoint(bottom_tickers)
    assert "T11" in top_tickers and "T0" in bottom_tickers


def test_volatility_none_with_insufficient_history():
    positions = [pos(1, "AAPL", 10, 100)]
    quotes = {"AAPL": quote("AAPL", 150)}
    hist = {"AAPL": history("AAPL", [100, 101, 102])}  # меньше MIN_POINTS_FOR_VOLATILITY
    result = build_dashboard(positions, quotes, RATE_USD_ONLY, "USD", hist)
    assert result.volatility[0].volatility_annualized is None
    assert result.volatility[0].data_points == 3


def test_volatility_computed_with_enough_history():
    positions = [pos(1, "AAPL", 10, 100)]
    quotes = {"AAPL": quote("AAPL", 150)}
    # Чередующиеся +1%/-1% дают ненулевую, разумную волатильность
    closes = [100 * (1.01 if i % 2 == 0 else 0.99) for i in range(30)]
    hist = {"AAPL": history("AAPL", closes)}
    result = build_dashboard(positions, quotes, RATE_USD_ONLY, "USD", hist)
    vol = result.volatility[0].volatility_annualized
    assert vol is not None and vol > 0
    assert result.portfolio_volatility_weighted == vol  # одна позиция -> совпадает


def test_annualized_volatility_zero_for_constant_price():
    closes = [100.0] * 20
    assert annualized_volatility(closes) == 0.0


def test_annualized_volatility_none_for_short_series():
    assert annualized_volatility([100, 101, 102]) is None
