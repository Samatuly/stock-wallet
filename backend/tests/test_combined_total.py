from datetime import date

from app.schemas import CurrencyTotal
from app.services.fx import RateTable
from app.services.portfolio import combine_totals


def totals(*rows):
    return [CurrencyTotal(currency=c, cost=cost, value=value, pnl_amount=value - cost,
                           pnl_percent=(value - cost) / cost * 100 if cost else None,
                           priced_count=1, unpriced_count=0) for c, cost, value in rows]


def test_combines_two_currencies_into_usd():
    table = RateTable(rates={"USD": 1.0, "EUR": 0.92}, as_of=date(2026, 9, 28), is_stale=False)
    result = combine_totals(totals(("USD", 1000, 1100), ("EUR", 500, 550)), "USD", table)
    # 550 EUR -> 550 / 0.92 = 597.83 USD
    assert result.currency == "USD"
    assert result.value == round(1100 + 550 / 0.92, 2)
    assert result.cost == round(1000 + 500 / 0.92, 2)
    assert result.missing_currencies == []
    assert not result.is_stale


def test_missing_rate_is_excluded_and_flagged():
    table = RateTable(rates={"USD": 1.0}, as_of=None, is_stale=True, missing=["KZT"])
    result = combine_totals(totals(("USD", 100, 120), ("KZT", 40000, 42000)), "USD", table)
    assert result.value == 120.0  # KZT-часть не добавлена, потому что курса нет
    assert result.missing_currencies == ["KZT"]
    assert result.is_stale


def test_empty_totals_gives_zero_without_error():
    table = RateTable(rates={"USD": 1.0}, as_of=date(2026, 9, 28), is_stale=False)
    result = combine_totals([], "USD", table)
    assert result.value == 0 and result.cost == 0 and result.pnl_percent is None
