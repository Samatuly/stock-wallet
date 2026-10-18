from datetime import date, datetime

from app.models import Position
from app.services.portfolio import build_portfolio
from app.services.quote_provider import Quote

NOW = datetime(2026, 9, 28, 12, 0)


def pos(id, ticker, qty, buy, fee=0.0, currency="USD", market="US"):
    return Position(
        id=id, ticker=ticker, market=market, quantity=qty, buy_price=buy,
        buy_date=date(2026, 1, 15), fee=fee, currency=currency, note="",
    )


def quote(ticker, price, currency="USD", source="finnhub", manual=False):
    return Quote(ticker, price, currency, source, NOW, manual)


def test_pnl_matches_doc_example():
    # Пример из документации: 10 акций по 180,50, цена 195,20 -> +147,00 (+8,14%)
    result = build_portfolio([pos(1, "AAPL", 10, 180.50)], {"AAPL": quote("AAPL", 195.20)})
    row = result.positions[0]
    assert row.value == 1952.00
    assert row.pnl_amount == 147.00
    assert row.pnl_percent == 8.14
    assert row.weight_percent == 100.0


def test_fee_is_part_of_cost():
    result = build_portfolio([pos(1, "AAPL", 10, 180.50, fee=5)], {"AAPL": quote("AAPL", 195.20)})
    row = result.positions[0]
    assert row.cost == 1810.00
    assert row.pnl_amount == 142.00
    assert row.pnl_percent == 7.85


def test_loss_is_negative():
    result = build_portfolio([pos(1, "AAPL", 10, 200)], {"AAPL": quote("AAPL", 190)})
    row = result.positions[0]
    assert row.pnl_amount == -100.00
    assert row.pnl_percent == -5.00


def test_missing_price_is_flagged_and_excluded_from_totals():
    result = build_portfolio(
        [pos(1, "AAPL", 10, 180.50), pos(2, "XYZ", 5, 10)],
        {"AAPL": quote("AAPL", 195.20), "XYZ": None},
    )
    xyz = result.positions[1]
    assert xyz.value is None and xyz.pnl_amount is None
    assert "вручную" in xyz.warning
    total = result.totals[0]
    assert total.currency == "USD"
    assert total.priced_count == 1 and total.unpriced_count == 1
    assert total.value == 1952.00


def test_currency_mismatch_blocks_calculation():
    # Лондон отдаёт цены в пенсах (GBp), позиция заведена в фунтах
    result = build_portfolio(
        [pos(1, "VOD.L", 100, 0.70, currency="GBP", market="EU")],
        {"VOD.L": quote("VOD.L", 72.0, currency="GBp", source="yfinance")},
    )
    row = result.positions[0]
    assert row.value is None and row.pnl_amount is None
    assert "GBp" in row.warning


def test_totals_and_weights_are_per_currency():
    result = build_portfolio(
        [
            pos(1, "AAPL", 10, 100),
            pos(2, "MSFT", 10, 100),
            pos(3, "SAP.DE", 10, 100, currency="EUR", market="EU"),
        ],
        {
            "AAPL": quote("AAPL", 150),
            "MSFT": quote("MSFT", 50),
            "SAP.DE": quote("SAP.DE", 120, currency="EUR", source="yfinance"),
        },
    )
    by_ccy = {t.currency: t for t in result.totals}
    assert by_ccy["USD"].value == 2000.00 and by_ccy["USD"].pnl_amount == 0.00
    assert by_ccy["EUR"].value == 1200.00 and by_ccy["EUR"].pnl_percent == 20.00
    weights = {r.ticker: r.weight_percent for r in result.positions}
    assert weights["AAPL"] == 75.0 and weights["MSFT"] == 25.0
    assert weights["SAP.DE"] == 100.0
