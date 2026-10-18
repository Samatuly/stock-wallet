"""Сравнение портфеля с индексом S&P 500: что было бы, если вложить ту же сумму
в индекс в те же даты, что и реальные покупки.

Упрощение, которое стоит знать: индекс торгуется в долларах США, а сравнение
идёт по доходности в процентах — колебания курса для позиций в других валютах
напрямую не учитываются (сама позиция в её валюте посчитана точно, но её вклад
в сравнение с индексом — приближённо). Это тот же класс допущений, что и у
упрощённой волатильности портфеля на дашборде.
"""
from __future__ import annotations

from datetime import date as date_

from app.models import Position, PriceHistory
from app.schemas import BenchmarkComparison
from app.services.fx import RateTable
from app.services.portfolio import build_portfolio

BENCHMARK_TICKER = "^GSPC"
BENCHMARK_NAME = "S&P 500"


def _price_on_or_before(rows: list[PriceHistory], target: date_) -> float | None:
    """Цена на дату покупки, либо ближайший предыдущий торговый день (если
    покупка пришлась на выходной или праздник)."""
    candidates = [r for r in rows if r.date <= target]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.date).close


def build_benchmark_comparison(
    positions: list[Position],
    quotes,
    fx_table: RateTable,
    display_currency: str,
    benchmark_history: list[PriceHistory],
) -> BenchmarkComparison | None:
    """benchmark_history — уже полученная история ^GSPC (см. роутер); так функцию
    можно тестировать без обращения к настоящему HistoryService."""
    if not positions or len(benchmark_history) < 2:
        return None

    display_currency = display_currency.upper()
    bench_latest = benchmark_history[-1].close
    portfolio = build_portfolio(positions, quotes)
    valuations = {v.id: v for v in portfolio.positions}

    total_cost = 0.0
    total_value = 0.0
    weighted_bench_return = 0.0
    weight_total = 0.0
    missing = set(fx_table.missing)
    skipped: list[str] = []

    for p in positions:
        v = valuations.get(p.id)
        if v is None or v.value is None:
            continue
        cost_display = fx_table.convert(v.cost, p.currency, display_currency)
        value_display = fx_table.convert(v.value, p.currency, display_currency)
        if cost_display is None or value_display is None:
            missing.add(p.currency)
            continue

        bench_then = _price_on_or_before(benchmark_history, p.buy_date)
        if not bench_then or bench_then <= 0:
            skipped.append(p.ticker)
            continue

        bench_return = bench_latest / bench_then - 1
        weighted_bench_return += bench_return * cost_display
        weight_total += cost_display
        total_cost += cost_display
        total_value += value_display

    if weight_total <= 0 or total_cost <= 0:
        return None

    oldest = min(p.buy_date for p in positions)
    return BenchmarkComparison(
        benchmark_name=BENCHMARK_NAME,
        display_currency=display_currency,
        portfolio_return_percent=round((total_value / total_cost - 1) * 100, 2),
        benchmark_return_percent=round(weighted_bench_return / weight_total * 100, 2),
        since_date=oldest,
        skipped_tickers=sorted(set(skipped)),
        missing_currencies=sorted(missing),
    )
