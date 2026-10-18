"""Дашборд портфеля: аллокация, волатильность, лидеры и аутсайдеры по доходности.

Волатильность каждой позиции — годовая, посчитана по дневным логарифмическим
доходностям из price_history (стандартное отклонение × √252 торговых дней).
Это стандартная, но упрощённая оценка: она не учитывает "тяжёлые хвосты" и
предполагает постоянную волатильность — то же допущение, что и в документе
проекта для Monte Carlo. Волатильность портфеля — средняя по позициям,
взвешенная по их доле в портфеле, а не настоящая портфельная волатильность
(та учитывала бы ещё и корреляции между бумагами, для этого нужна общая
история цен по одинаковым датам — сделаем на следующем шаге, если понадобится).
"""
from __future__ import annotations

import math
from typing import Optional

from app.models import PriceHistory
from app.schemas import AllocationItem, BenchmarkComparison, DashboardOut, PositionRisk, PositionValuation
from app.services.fx import RateTable
from app.services.portfolio import build_portfolio

TRADING_DAYS_PER_YEAR = 252
MIN_POINTS_FOR_VOLATILITY = 10


def _allocation(groups: dict[str, float], total: float) -> list[AllocationItem]:
    items = [
        AllocationItem(
            label=label,
            value=round(value, 2),
            percent=round(value / total * 100, 2) if total > 0 else 0.0,
        )
        for label, value in groups.items()
    ]
    return sorted(items, key=lambda i: i.value, reverse=True)


def annualized_volatility(closes: list[float]) -> Optional[float]:
    """Годовая волатильность в процентах, или None, если истории мало."""
    if len(closes) < MIN_POINTS_FOR_VOLATILITY:
        return None
    returns = []
    for prev, cur in zip(closes, closes[1:]):
        if prev > 0 and cur > 0:
            returns.append(math.log(cur / prev))
    if len(returns) < MIN_POINTS_FOR_VOLATILITY - 1:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    daily_vol = math.sqrt(variance)
    return round(daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2)


def build_dashboard(
    positions,
    quotes,
    fx_table: RateTable,
    display_currency: str,
    history: dict[str, list[PriceHistory]],
    benchmark: Optional[BenchmarkComparison] = None,
) -> DashboardOut:
    portfolio = build_portfolio(positions, quotes)
    display_currency = display_currency.upper()
    missing = set(fx_table.missing)

    def to_display(amount: float, ccy: str) -> Optional[float]:
        converted = fx_table.convert(amount, ccy, display_currency)
        if converted is None:
            missing.add(ccy)
        return converted

    priced: list[tuple[PositionValuation, float]] = []  # позиция + стоимость в display_currency
    total_value = 0.0
    by_market: dict[str, float] = {}
    by_currency: dict[str, float] = {}
    by_ticker: dict[str, float] = {}

    for p in portfolio.positions:
        if p.value is None:
            continue
        v = to_display(p.value, p.currency)
        if v is None:
            continue
        priced.append((p, v))
        total_value += v
        by_market[p.market] = by_market.get(p.market, 0.0) + v
        by_currency[p.currency] = by_currency.get(p.currency, 0.0) + v
        by_ticker[p.ticker] = by_ticker.get(p.ticker, 0.0) + v

    ranked = sorted(
        (p for p, _ in priced if p.pnl_percent is not None),
        key=lambda p: p.pnl_percent,
        reverse=True,
    )
    top = ranked[:5]
    # Не дублируем позиции между "лидерами" и "аутсайдерами", если бумаг мало
    remaining = ranked[5:]
    bottom = list(reversed(remaining[-5:])) if remaining else []

    vol_list: list[PositionRisk] = []
    weighted_sum = 0.0
    weight_total = 0.0
    for p, value in priced:
        closes = [h.close for h in history.get(p.ticker, [])]
        vol = annualized_volatility(closes)
        vol_list.append(PositionRisk(ticker=p.ticker, volatility_annualized=vol, data_points=len(closes)))
        if vol is not None:
            weighted_sum += vol * value
            weight_total += value

    portfolio_vol = round(weighted_sum / weight_total, 2) if weight_total > 0 else None

    return DashboardOut(
        display_currency=display_currency,
        total_value=round(total_value, 2),
        allocation_by_market=_allocation(by_market, total_value),
        allocation_by_currency=_allocation(by_currency, total_value),
        allocation_by_ticker=_allocation(by_ticker, total_value),
        top_positions=top,
        bottom_positions=bottom,
        volatility=vol_list,
        portfolio_volatility_weighted=portfolio_vol,
        rate_date=fx_table.as_of,
        missing_currencies=sorted(missing),
        benchmark=benchmark,
    )
