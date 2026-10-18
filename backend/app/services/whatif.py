"""Сценарий «что-если»: пересчёт портфеля при заданных изменениях цен и курсов.

Это простая арифметика над текущими данными, без Claude и без прогноза. Она отвечает
на вопрос «сколько стоил бы портфель, если...», а не «что будет». Корреляции между
акциями и реакцию рынка не моделируем: каждое изменение применяется как задано.
"""
from __future__ import annotations

from app.schemas import PositionValuation, WhatIfPosition, WhatIfRequest, WhatIfResult
from app.services.fx import RateTable


def simulate_what_if(
    positions: list[PositionValuation], req: WhatIfRequest, table: RateTable
) -> WhatIfResult:
    display = req.display_currency
    rows: list[WhatIfPosition] = []
    skipped: list[str] = []
    now_total = after_total = cost_total = 0.0

    for p in positions:
        value_local = p.value
        value_now = table.convert(value_local, p.currency, display) if value_local is not None else None
        cost = table.convert(p.cost, p.currency, display)
        if value_now is None or cost is None:
            skipped.append(p.ticker)
            continue

        price_pct = req.ticker_shocks.get(p.ticker, req.market_shocks.get(p.market, 0.0))
        fx_pct = 0.0 if p.currency == display else req.fx_shocks.get(p.currency, 0.0)
        value_after = value_now * (1 + price_pct / 100) * (1 + fx_pct / 100)

        now_total += value_now
        after_total += value_after
        cost_total += cost
        rows.append(
            WhatIfPosition(
                ticker=p.ticker, market=p.market, currency=p.currency,
                value_now=round(value_now, 2), value_after=round(value_after, 2),
                delta=round(value_after - value_now, 2),
                price_change_percent=price_pct, fx_change_percent=fx_pct,
            )
        )

    delta = after_total - now_total
    return WhatIfResult(
        display_currency=display,
        value_now=round(now_total, 2),
        value_after=round(after_total, 2),
        delta=round(delta, 2),
        delta_percent=round(delta / now_total * 100, 2) if now_total > 0 else None,
        cost=round(cost_total, 2),
        pnl_now=round(now_total - cost_total, 2),
        pnl_after=round(after_total - cost_total, 2),
        positions=rows,
        skipped_tickers=sorted(set(skipped)),
        rate_date=table.as_of,
    )
