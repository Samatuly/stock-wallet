import math

import pytest

from app.services.monte_carlo import estimate_mu_sigma, simulate


def test_estimate_mu_sigma_zero_for_constant_price():
    mu, sigma = estimate_mu_sigma([100.0] * 30)
    assert mu == pytest.approx(0, abs=1e-9)
    assert sigma == pytest.approx(0, abs=1e-9)


def test_estimate_mu_sigma_positive_for_rising_price():
    closes = [100 * (1.01**i) for i in range(60)]  # устойчивый рост на 1% в день
    mu, sigma = estimate_mu_sigma(closes)
    assert mu > 0
    assert sigma == pytest.approx(0, abs=1e-6)  # доходность постоянная -> волатильность ~0


def test_simulate_zero_volatility_gives_deterministic_result():
    # При нулевой волатильности все пути одинаковы -> p10 == p50 == p90
    result = simulate(current_price=100, mu_annual=0.0, sigma_annual=0.0, horizon_days=30, n_paths=200, seed=1)
    assert result.p10 == result.p50 == result.p90 == pytest.approx(100, rel=1e-6)


def test_simulate_median_close_to_price_when_mu_is_zero():
    result = simulate(current_price=100, mu_annual=0.0, sigma_annual=0.3, horizon_days=30, n_paths=20000, seed=42)
    # При нулевом дрейфе медиана geometric Brownian motion немного ниже текущей цены
    # (из-за члена -sigma^2/2), но должна быть в разумных пределах
    assert 85 < result.p50 < 100


def test_simulate_p10_less_than_p90():
    result = simulate(current_price=100, mu_annual=0.05, sigma_annual=0.25, horizon_days=90, n_paths=5000, seed=7)
    assert result.p10 < result.p50 < result.p90


def test_simulate_prob_above_buy_price_monotonic():
    result = simulate(current_price=150, mu_annual=0.1, sigma_annual=0.2, horizon_days=30,
                       buy_price=100, n_paths=5000, seed=3)
    # Цена сильно выше цены покупки -> вероятность быть выше должна быть высокой
    assert result.prob_above_buy_price > 0.9


def test_simulate_prob_above_buy_price_low_when_buy_price_far_above():
    result = simulate(current_price=100, mu_annual=0.0, sigma_annual=0.2, horizon_days=30,
                       buy_price=200, n_paths=5000, seed=3)
    assert result.prob_above_buy_price < 0.05


def test_simulate_none_when_no_buy_price():
    result = simulate(current_price=100, mu_annual=0.0, sigma_annual=0.2, horizon_days=30, n_paths=100, seed=1)
    assert result.prob_above_buy_price is None


def test_simulate_is_reproducible_with_same_seed():
    r1 = simulate(current_price=100, mu_annual=0.05, sigma_annual=0.2, horizon_days=30, n_paths=500, seed=99)
    r2 = simulate(current_price=100, mu_annual=0.05, sigma_annual=0.2, horizon_days=30, n_paths=500, seed=99)
    assert r1 == r2


def test_simulate_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        simulate(current_price=0, mu_annual=0, sigma_annual=0.2, horizon_days=30)
    with pytest.raises(ValueError):
        simulate(current_price=100, mu_annual=0, sigma_annual=0.2, horizon_days=0)
