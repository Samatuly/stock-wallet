"""Базовые ожидаемые доходности рынков (J.P. Morgan LTCMA 2026, 10–15 лет, в год).

Это ориентир «что рынок в среднем даёт», с которым сравнивается прогноз по
конкретной акции. Это допущения аналитиков банка, а не гарантия. Обновляйте
цифры раз в год, когда выходит новый отчёт.
"""
from typing import NamedTuple


class Baseline(NamedTuple):
    key: str
    name: str
    annual_return_percent: float


BASELINES = {
    "us_large_cap": Baseline("us_large_cap", "Крупные акции США", 6.7),
    "developed_ex_us": Baseline("developed_ex_us", "Развитые рынки вне США (EAFE)", 7.4),
    "emerging_markets": Baseline("emerging_markets", "Развивающиеся рынки", 7.8),
    "global": Baseline("global", "Глобальные акции", 7.0),
}

MARKET_TO_BASELINE = {"US": "us_large_cap", "EU": "developed_ex_us", "KZ": "emerging_markets"}


def baseline_for_market(market: str) -> Baseline:
    return BASELINES[MARKET_TO_BASELINE.get(market, "global")]
