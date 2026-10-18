from datetime import date, timedelta

from app.models import Position, PriceHistory
from app.services.benchmark import build_benchmark_comparison
from app.services.fx import RateTable
from app.services.quote_provider import Quote


def pos(id, ticker, qty, buy, buy_date_, currency="USD", market="US"):
    return Position(
        id=id, ticker=ticker, market=market, quantity=qty, buy_price=buy,
        buy_date=buy_date_, fee=0.0, currency=currency, note="",
    )


def quote(ticker, price, currency="USD"):
    return Quote(ticker, price, currency, "finnhub", date(2026, 9, 30))


def bench(prices: dict):
    """prices: {date: close}"""
    return [PriceHistory(ticker="^GSPC", date=d, open=c, high=c, low=c, close=c, volume=0, fetched_at=None)
            for d, c in sorted(prices.items())]


RATE_USD = RateTable(rates={"USD": 1.0}, as_of=date(2026, 9, 30), is_stale=False)


def test_matches_hand_calculation_single_position():
    # Купили на 1000$ в день, когда индекс был 4000; сейчас индекс 4400 (+10%).
    # Акция сама выросла до 1200$ (+20%). Портфель должен обгонять индекс.
    positions = [pos(1, "AAPL", 10, 100, date(2026, 1, 1))]
    quotes = {"AAPL": quote("AAPL", 120)}
    history = bench({date(2026, 1, 1): 4000, date(2026, 9, 30): 4400})
    result = build_benchmark_comparison(positions, quotes, RATE_USD, "USD", history)
    assert result.portfolio_return_percent == 20.0
    assert result.benchmark_return_percent == 10.0


def test_weighted_by_cost_across_two_positions():
    positions = [
        pos(1, "A", 10, 100, date(2026, 1, 1)),  # 1000$, индекс тогда 4000 -> +10% к текущим 4400
        pos(2, "B", 1, 1000, date(2026, 6, 1)),  # 1000$, индекс тогда 4300 -> +2.33% к 4400
    ]
    quotes = {"A": quote("A", 110), "B": quote("B", 1000)}
    history = bench({date(2026, 1, 1): 4000, date(2026, 6, 1): 4300, date(2026, 9, 30): 4400})
    result = build_benchmark_comparison(positions, quotes, RATE_USD, "USD", history)
    # Равные веса по 1000$ -> среднее двух доходностей индекса
    expected = ((4400 / 4000 - 1) + (4400 / 4300 - 1)) / 2 * 100
    assert result.benchmark_return_percent == round(expected, 2)


def test_uses_previous_trading_day_when_buy_date_falls_on_weekend():
    # Пятница 2026-01-02 — последняя цена перед выходными; покупка в субботу
    positions = [pos(1, "AAPL", 10, 100, date(2026, 1, 3))]  # суббота
    quotes = {"AAPL": quote("AAPL", 110)}
    history = bench({date(2026, 1, 2): 4000, date(2026, 9, 30): 4400})  # пятница + сегодня
    result = build_benchmark_comparison(positions, quotes, RATE_USD, "USD", history)
    assert result.benchmark_return_percent == 10.0  # взята цена пятницы


def test_position_older_than_benchmark_history_is_skipped_not_crashed():
    positions = [
        pos(1, "OLD", 1, 100, date(2000, 1, 1)),  # индекса на эту дату нет вообще
        pos(2, "NEW", 1, 100, date(2026, 1, 1)),
    ]
    quotes = {"OLD": quote("OLD", 110), "NEW": quote("NEW", 110)}
    history = bench({date(2026, 1, 1): 4000, date(2026, 9, 30): 4400})
    result = build_benchmark_comparison(positions, quotes, RATE_USD, "USD", history)
    assert result.skipped_tickers == ["OLD"]
    # В расчёте участвует только NEW
    assert result.benchmark_return_percent == 10.0


def test_returns_none_when_no_positions():
    assert build_benchmark_comparison([], {}, RATE_USD, "USD", bench({date(2026, 1, 1): 4000})) is None


def test_returns_none_when_benchmark_history_too_short():
    positions = [pos(1, "AAPL", 10, 100, date(2026, 1, 1))]
    quotes = {"AAPL": quote("AAPL", 110)}
    assert build_benchmark_comparison(positions, quotes, RATE_USD, "USD", []) is None
    assert build_benchmark_comparison(positions, quotes, RATE_USD, "USD", bench({date(2026, 1, 1): 4000})) is None


def test_missing_fx_rate_is_reported_and_position_excluded():
    positions = [
        pos(1, "AAPL", 10, 100, date(2026, 1, 1), currency="USD"),
        pos(2, "SAP.DE", 10, 100, date(2026, 1, 1), currency="EUR", market="EU"),
    ]
    quotes = {"AAPL": quote("AAPL", 110), "SAP.DE": Quote("SAP.DE", 110, "EUR", "yfinance", date(2026, 9, 30))}
    history = bench({date(2026, 1, 1): 4000, date(2026, 9, 30): 4400})
    result = build_benchmark_comparison(positions, quotes, RATE_USD, "USD", history)  # RATE_USD не знает EUR
    assert "EUR" in result.missing_currencies
    assert result.benchmark_return_percent == 10.0  # посчитано только по USD-позиции
