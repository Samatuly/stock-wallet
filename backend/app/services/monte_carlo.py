"""Monte Carlo симуляция цены: геометрическое броуновское движение.

S_{t+1} = S_t * exp((μ - σ²/2)Δt + σ√Δt·Z), Z ~ N(0,1)

Это учебная, стандартная в финансах модель, не более того: она предполагает
постоянную волатильность и не учитывает "тяжёлые хвосты" (редкие резкие
обвалы или скачки). Дрейф (μ) оценивается по исторической доходности, которая
сама по себе очень шумная — поэтому результат стоит воспринимать как диапазон
при заданных допущениях, а не предсказание будущего.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

TRADING_DAYS_PER_YEAR = 252


@dataclass
class MonteCarloResult:
    p10: float
    p50: float
    p90: float
    prob_above_buy_price: float | None  # None, если buy_price не задан
    paths: int
    horizon_days: int
    mu_annual: float
    sigma_annual: float


def estimate_mu_sigma(closes: list[float]) -> tuple[float, float]:
    """Годовые дрейф и волатильность по дневным логарифмическим доходностям."""
    returns = []
    for prev, cur in zip(closes, closes[1:]):
        if prev > 0 and cur > 0:
            returns.append(math.log(cur / prev))
    if len(returns) < 2:
        return 0.0, 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    sigma_daily = math.sqrt(variance)
    return mean * TRADING_DAYS_PER_YEAR, sigma_daily * math.sqrt(TRADING_DAYS_PER_YEAR)


def simulate(
    current_price: float,
    mu_annual: float,
    sigma_annual: float,
    horizon_days: int,
    buy_price: float | None = None,
    n_paths: int = 5000,
    seed: int | None = None,
) -> MonteCarloResult:
    if current_price <= 0 or horizon_days <= 0:
        raise ValueError("цена и горизонт должны быть положительными")

    rng = random.Random(seed)
    dt = 1 / TRADING_DAYS_PER_YEAR
    drift = (mu_annual - sigma_annual**2 / 2) * horizon_days * dt
    vol = sigma_annual * math.sqrt(horizon_days * dt)

    finals = []
    above = 0
    for _ in range(n_paths):
        z = rng.gauss(0, 1)
        price = current_price * math.exp(drift + vol * z)
        finals.append(price)
        if buy_price is not None and price > buy_price:
            above += 1

    finals.sort()
    def pct(p: float) -> float:
        idx = min(int(p * len(finals)), len(finals) - 1)
        return finals[idx]

    return MonteCarloResult(
        p10=round(pct(0.10), 4),
        p50=round(pct(0.50), 4),
        p90=round(pct(0.90), 4),
        prob_above_buy_price=round(above / n_paths, 4) if buy_price is not None else None,
        paths=n_paths,
        horizon_days=horizon_days,
        mu_annual=round(mu_annual, 4),
        sigma_annual=round(sigma_annual, 4),
    )
