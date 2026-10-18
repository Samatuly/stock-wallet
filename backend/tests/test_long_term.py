import json
from datetime import date, timedelta

import pytest

from app.models import Forecast, LongTermForecast
from app.schemas import LongTermScenarioInput
from app.services.accuracy import AccuracyService
from app.services.claude_client import ClaudeTruncatedError
from app.services.forecast import BudgetExceededError, ForecastError, ForecastService
from app.services.fundamentals import Fundamentals, FundamentalsService
from app.services.history import Candle, HistoryService
from app.services.long_term import (
    LongTermForecastService,
    build_output,
    compute_scenario,
    weighted_annual_total_percent,
)
from app.services.market_baseline import baseline_for_market


def scenario(name="base", p=1.0, g=0.05, b=0.01, m=0.0, v=0.0):
    return LongTermScenarioInput(
        name=name, probability=p, revenue_growth_annual=g, net_buyback_annual=b,
        margin_change_annual=m, valuation_change_annual=v, rationale="тест",
    )


def good_claude(note="", base_g=0.05):
    return {
        "summary": "Долгосрочно ровный рост.",
        "scenarios": [
            {"name": "optimistic", "probability": 0.25, "revenue_growth_annual": base_g + 0.03, "net_buyback_annual": 0.01,
             "margin_change_annual": 0.005, "valuation_change_annual": 0.0, "rationale": "лучше"},
            {"name": "base", "probability": 0.5, "revenue_growth_annual": base_g, "net_buyback_annual": 0.01,
             "margin_change_annual": 0.0, "valuation_change_annual": 0.0, "rationale": "база"},
            {"name": "pessimistic", "probability": 0.25, "revenue_growth_annual": base_g - 0.04, "net_buyback_annual": 0.0,
             "margin_change_annual": -0.005, "valuation_change_annual": -0.01, "rationale": "хуже"},
        ],
        "benchmark_comparison_note": note,
        "confidence": "low",
        "data_gaps": ["нет данных по выручке"],
    }


# ---- чистая арифметика (посчитана вручную) ----

def test_compute_scenario_hand_calculated():
    # factor = 1.05 * 1.01 = 1.0605; цена через 5 лет = 100 * 1.0605^5 = 134.14
    ap, at, points = compute_scenario(100.0, scenario(), dividend_yield=0.01)
    assert ap == pytest.approx(0.0605)
    assert at == pytest.approx(0.0705)
    by_year = {p.years: p for p in points}
    assert by_year[1].price == pytest.approx(106.05)
    assert by_year[5].price == pytest.approx(134.14, abs=0.01)
    assert by_year[10].price == pytest.approx(179.94, abs=0.02)
    # полная доходность за 5 лет: 1.0705^5 - 1 = 40.58%
    assert by_year[5].total_return_percent == pytest.approx(40.58, abs=0.02)


def test_compute_scenario_zero_assumptions_keeps_price():
    ap, at, points = compute_scenario(50.0, scenario(g=0, b=0), dividend_yield=0.0)
    assert ap == 0 and at == 0
    assert all(p.price == 50.0 and p.total_return_percent == 0 for p in points)


def test_weighted_return():
    a = scenario("optimistic", 0.5, g=0.10, b=0.0)
    b = scenario("pessimistic", 0.5, g=0.0, b=0.0)
    assert weighted_annual_total_percent([a, b], 0.02) == pytest.approx(7.0)  # 0.5*12 + 0.5*2


def test_baseline_mapping():
    assert baseline_for_market("US").annual_return_percent == 6.7
    assert baseline_for_market("EU").annual_return_percent == 7.4
    assert baseline_for_market("KZ").annual_return_percent == 7.8
    assert baseline_for_market("XX").key == "global"


def test_schema_rejects_percent_instead_of_fraction():
    with pytest.raises(Exception):
        scenario(g=5.0)  # 5 — это 500% в год, скорее всего перепутали с процентами


# ---- сервис ----

class FakeClaude:
    max_tokens = 4096

    def __init__(self, responses, truncate_first=False):
        self.responses = list(responses)
        self.calls = []
        self.truncate_first = truncate_first
        self._done = False

    def complete_json(self, package, extra_instruction=None, previous_response_text=None,
                      max_tokens_override=None, system_prompt=None):
        self.calls.append({"extra": extra_instruction, "tokens": max_tokens_override, "system": system_prompt})
        if self.truncate_first and not self._done:
            self._done = True
            raise ClaudeTruncatedError("обрыв", input_tokens=400, output_tokens=4096)

        class R:
            pass

        r = R()
        r.text = self.responses.pop(0)
        r.input_tokens, r.output_tokens = 1000, 800
        return r


class HistProvider:
    def fetch(self, ticker, days):
        today = date.today()
        return [Candle(date=today - timedelta(days=i), open=1, high=1, low=1, close=100 + i * 0.05, volume=1)
                for i in range(1500, -1, -1)]


class FundProvider:
    def fetch(self, ticker):
        return {"trailingPE": 25.0, "dividendRate": 1.0, "currentPrice": 100.0}


def make_service(db, claude, budget=10.0):
    hist = HistoryService(db, HistProvider())
    fund = FundamentalsService(db, FundProvider())
    fs = ForecastService(db, claude, hist, fund, monthly_budget_usd=budget)
    return LongTermForecastService(db, claude, hist, fund, budget_service=fs)


def test_create_computes_prices_in_code_and_saves(db):
    claude = FakeClaude([json.dumps(good_claude(base_g=0.04))])
    svc = make_service(db, claude)
    row = svc.create("AAPL", "US", 100.0, "USD")
    out = build_output(row, from_cache=False)

    base = next(s for s in out.scenarios if s.name == "base")
    assert [p.years for p in base.points] == [1, 5, 10]
    # цену посчитал код: factor = 1.04*1.01
    assert base.points[0].price == pytest.approx(100 * 1.04 * 1.01, abs=0.01)
    assert out.benchmark_return_percent == 6.7
    assert [s.name for s in out.scenarios] == ["optimistic", "base", "pessimistic"]
    assert row.cost_usd == pytest.approx(1000 / 1e6 * 2 + 800 / 1e6 * 10)
    assert claude.calls[0]["system"] is not None  # используется долгосрочный промпт
    assert svc.get_cached("AAPL") is not None


def test_large_gap_without_note_triggers_retry(db):
    # База 12% роста: взвешенная доходность сильно выше 6.7% ориентира
    bad = good_claude(note="", base_g=0.12)
    fixed = good_claude(note="Выше рынка, потому что предполагаем высокий рост выручки и выкуп акций.", base_g=0.12)
    claude = FakeClaude([json.dumps(bad), json.dumps(fixed)])
    row = make_service(db, claude).create("AAPL", "US", 100.0, "USD")
    assert len(claude.calls) == 2
    assert "п.п." in claude.calls[1]["extra"]
    assert "Выше рынка" in build_output(row, False).benchmark_comparison_note
    assert row.input_tokens == 2000  # токены обеих попыток учтены


def test_large_gap_without_note_twice_fails(db):
    bad = json.dumps(good_claude(note="", base_g=0.12))
    claude = FakeClaude([bad, bad])
    with pytest.raises(ForecastError):
        make_service(db, claude).create("AAPL", "US", 100.0, "USD")
    assert db.query(LongTermForecast).count() == 0


def test_probability_sum_retry(db):
    broken = good_claude()
    broken["scenarios"][0]["probability"] = 0.6
    claude = FakeClaude([json.dumps(broken), json.dumps(good_claude())])
    make_service(db, claude).create("AAPL", "US", 100.0, "USD")
    assert len(claude.calls) == 2


def test_truncation_retries_with_double_tokens_and_counts_cost(db):
    claude = FakeClaude([json.dumps(good_claude())], truncate_first=True)
    row = make_service(db, claude).create("AAPL", "US", 100.0, "USD")
    assert claude.calls[1]["tokens"] == 8192
    assert row.input_tokens == 1400 and row.output_tokens == 4896


def test_budget_blocks_and_counts_long_term_spend(db):
    claude = FakeClaude([json.dumps(good_claude()), json.dumps(good_claude())])
    svc = make_service(db, claude, budget=0.01)
    svc.create("AAPL", "US", 100.0, "USD")  # стоит ~$0.01, лимит исчерпан
    with pytest.raises(BudgetExceededError):
        svc.create("MSFT", "US", 100.0, "USD")
    assert svc.budget_service.get_monthly_spend() >= 0.01


# ---- точность ----

def add_forecast(db, created, horizon, price, low, high, p50, actual=None):
    combined = {
        "monte_carlo": {"p10": 1, "p50": p50, "p90": 2, "prob_above_buy_price": None, "paths": 1,
                        "mu_annual": 0, "sigma_annual": 0},
        "result": {"scenarios": [{"name": "base", "probability": 1, "price_low": low, "price_high": high, "drivers": []}]},
    }
    db.add(Forecast(ticker="AAPL", market="US", horizon_days=horizon, created_at=created,
                    price_at_forecast=price, currency="USD", result_json=json.dumps(combined),
                    confidence="low", actual_price=actual))
    db.commit()


class FixedHistory:
    """Даёт цену закрытия 110 на каждый день."""

    def get_history(self, ticker, days=365, force=False):
        today = date(2026, 10, 18)
        return [Candle(date=today - timedelta(days=i), open=1, high=1, low=1, close=110, volume=1)
                for i in range(days, -1, -1)]


class _H:  # удобная обёртка: Candle не имеет всех полей PriceHistory, но нам нужны date/close
    pass


def test_accuracy_fills_actual_and_computes_metrics(db):
    from datetime import datetime
    now = datetime(2026, 10, 18, 12, 0)
    add_forecast(db, datetime(2026, 9, 1), 30, price=100, low=105, high=115, p50=104)   # созрел, попал
    add_forecast(db, datetime(2026, 9, 2), 30, price=100, low=90, high=100, p50=95)     # созрел, мимо
    add_forecast(db, datetime(2026, 10, 10), 30, price=100, low=1, high=2, p50=1)       # ещё не созрел

    svc = AccuracyService(db, FixedHistory(), now=lambda: now)
    s = svc.summary()
    assert s.total_evaluated == 2 and s.total_pending == 1
    assert s.hit_rate_base_range_percent == 50.0
    # ошибки vs p50: (110-104)/104=5.77%, (110-95)/95=15.79% → среднее 10.78
    assert s.mean_abs_pct_error_vs_monte_carlo_p50 == pytest.approx(10.78, abs=0.01)
    assert s.mean_abs_pct_error_naive == 10.0
    pending = [i for i in s.items if i.actual_price is None]
    assert len(pending) == 1 and pending[0].hit_base_range is None
    # значение сохранено в базе
    assert db.query(Forecast).filter(Forecast.actual_price.isnot(None)).count() == 2


def test_accuracy_waits_when_history_missing(db):
    from datetime import datetime

    class Empty:
        def get_history(self, *a, **k):
            return []

    add_forecast(db, datetime(2026, 9, 1), 30, 100, 90, 100, 95)
    s = AccuracyService(db, Empty(), now=lambda: datetime(2026, 10, 18)).summary()
    assert s.total_evaluated == 0 and s.total_pending == 1
    assert s.hit_rate_base_range_percent is None
