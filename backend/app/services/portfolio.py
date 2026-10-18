"""Расчёт прибыли и убытка. Курсы валют пока не применяются: итоги считаются по каждой валюте отдельно."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from app.models import Position
from app.schemas import CombinedTotal, CurrencyTotal, PortfolioOut, PositionOut, PositionValuation
from app.services.fx import RateTable
from app.services.quote_provider import Quote


def _r(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else round(value, digits)


def build_portfolio(positions: list[Position], quotes: dict[str, Optional[Quote]]) -> PortfolioOut:
    rows: list[PositionValuation] = []

    for p in positions:
        cost = p.quantity * p.buy_price + p.fee
        quote = quotes.get(p.ticker.upper())
        base = PositionValuation(
            **PositionOut.model_validate(p).model_dump(), cost=round(cost, 2)
        )

        if quote is None:
            base.warning = "Нет цены: задайте её вручную"
            rows.append(base)
            continue

        base.current_price = round(quote.price, 4)
        base.price_source = quote.source
        base.price_time = quote.fetched_at
        base.price_is_manual = quote.is_manual

        # Например, Лондонская биржа отдаёт цены в пенсах (GBp), а позиция заведена в фунтах (GBP).
        if quote.currency and quote.currency != p.currency:
            base.warning = (
                f"Валюта цены ({quote.currency}) не совпадает с валютой позиции ({p.currency}): "
                "результат не рассчитан"
            )
            rows.append(base)
            continue

        value = p.quantity * quote.price
        pnl = value - cost
        base.value = round(value, 2)
        base.pnl_amount = round(pnl, 2)
        base.pnl_percent = round(pnl / cost * 100, 2) if cost > 0 else None
        rows.append(base)

    # Итоги и доли по валютам, только по позициям с рассчитанным результатом
    agg: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "value": 0.0, "priced": 0, "unpriced": 0})
    for r in rows:
        bucket = agg[r.currency]
        if r.value is None:
            bucket["unpriced"] += 1
        else:
            bucket["cost"] += r.cost
            bucket["value"] += r.value
            bucket["priced"] += 1

    for r in rows:
        total_value = agg[r.currency]["value"]
        if r.value is not None and total_value > 0:
            r.weight_percent = round(r.value / total_value * 100, 2)

    totals = []
    for currency in sorted(agg):
        b = agg[currency]
        pnl = b["value"] - b["cost"]
        totals.append(
            CurrencyTotal(
                currency=currency,
                cost=round(b["cost"], 2),
                value=round(b["value"], 2),
                pnl_amount=round(pnl, 2),
                pnl_percent=round(pnl / b["cost"] * 100, 2) if b["cost"] > 0 else None,
                priced_count=b["priced"],
                unpriced_count=b["unpriced"],
            )
        )

    return PortfolioOut(positions=rows, totals=totals)


def combine_totals(totals: list[CurrencyTotal], display_currency: str, table: RateTable) -> CombinedTotal:
    """Складывает итоги по всем валютам в одну, используя курсы из table."""
    display_currency = display_currency.upper()
    value = cost = 0.0
    missing = set(table.missing)

    for t in totals:
        v = table.convert(t.value, t.currency, display_currency)
        c = table.convert(t.cost, t.currency, display_currency)
        if v is None or c is None:
            missing.add(t.currency)
            continue
        value += v
        cost += c

    pnl = value - cost
    return CombinedTotal(
        currency=display_currency,
        value=round(value, 2),
        cost=round(cost, 2),
        pnl_amount=round(pnl, 2),
        pnl_percent=round(pnl / cost * 100, 2) if cost > 0 else None,
        rate_date=table.as_of,
        is_stale=table.is_stale,
        missing_currencies=sorted(missing),
    )
