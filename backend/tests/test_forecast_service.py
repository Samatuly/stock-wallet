import json
from datetime import date, timedelta

import pytest

from app.models import Forecast, PriceHistory
from app.services.claude_client import ClaudeError, ClaudeTruncatedError
from app.services.forecast import BudgetExceededError, ForecastError, ForecastService
from app.services.fundamentals import Fundamentals, FundamentalsService
from app.services.history import Candle, HistoryService


GOOD_RESULT = {
    "summary": "Акция в боковике, краткосрочно без резких движений.",
    "scenarios": [
        {"name": "optimistic", "probability": 0.25, "price_low": 110, "price_high": 120, "drivers": ["рост спроса"]},
        {"name": "base", "probability": 0.5, "price_low": 100, "price_high": 110, "drivers": ["нейтральный фон"]},
        {"name": "pessimistic", "probability": 0.25, "price_low": 90, "price_high": 100, "drivers": ["риск отчёта"]},
    ],
    "prob_above_buy_price": 0.6,
    "key_risks": ["волатильность рынка"],
    "confidence": "medium",
    "data_gaps": [],
}


class FakeClaude:
    def __init__(self, responses, truncate_first=False):
        """responses: список текстов JSON, отдаются по очереди при каждом вызове.
        truncate_first: если True, самый первый вызов бросает ClaudeTruncatedError
        вместо того, чтобы отдать ответ (имитация обрыва по max_tokens)."""
        self.responses = list(responses)
        self.calls = []
        self.truncate_first = truncate_first
        self._truncated_once = False
        self.max_tokens = 1500  # как у настоящего ClaudeClient по умолчанию

    def complete_json(self, package, extra_instruction=None, previous_response_text=None, max_tokens_override=None, system_prompt=None):
        self.calls.append((package, extra_instruction, max_tokens_override))

        if self.truncate_first and not self._truncated_once:
            self._truncated_once = True
            raise ClaudeTruncatedError("оборвался на середине", input_tokens=400, output_tokens=1500)

        text = self.responses.pop(0)

        class R:
            def __init__(self_, text):
                self_.text = text
                self_.input_tokens = 500
                self_.output_tokens = 200

        return R(text)


class FakeHistoryProvider:
    def fetch(self, ticker, days):
        today = date.today()
        return [
            Candle(date=today - timedelta(days=i), open=100, high=101, low=99, close=100 + (i % 5), volume=1000)
            for i in range(days, 0, -1)
        ]


class FakeFundamentalsProvider:
    def fetch(self, ticker):
        return {"trailingPE": 20.0}


def make_service(db, clock, claude_responses, monthly_budget=10.0, truncate_first=False):
    history_service = HistoryService(db, FakeHistoryProvider(), now=clock)
    fundamentals_service = FundamentalsService(db, FakeFundamentalsProvider(), now=clock)
    claude = FakeClaude(claude_responses, truncate_first=truncate_first)
    svc = ForecastService(
        db, claude, history_service, fundamentals_service,
        now=clock, monthly_budget_usd=monthly_budget,
    )
    return svc, claude


def test_retries_once_with_doubled_tokens_when_response_is_truncated(db, clock):
    """Регрессия: 'Unterminated string...' при разборе JSON на самом деле означало,
    что Claude не уложился в max_tokens. Сервис должен сам повторить запрос
    с удвоенным лимитом, а не сразу падать с невнятной ошибкой."""
    svc, claude = make_service(db, clock, [json.dumps(GOOD_RESULT)], truncate_first=True)
    row = svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")
    assert len(claude.calls) == 2
    assert claude.calls[0][2] is None  # первый вызов — обычный лимит
    assert claude.calls[1][2] == svc.claude.max_tokens * 2  # второй — удвоенный
    combined = row.result()
    assert combined["result"]["confidence"] == "medium"


def test_truncated_call_tokens_are_counted_in_cost(db, clock):
    svc, claude = make_service(db, clock, [json.dumps(GOOD_RESULT)], truncate_first=True)
    row = svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")
    # Неудачная (оборванная) попытка потратила 400 вход / 1500 выход токенов —
    # они должны быть учтены в стоимости вместе с успешной попыткой (500/200).
    expected_cost = round((400 + 500) / 1_000_000 * 2.0 + (1500 + 200) / 1_000_000 * 10.0, 6)
    assert row.cost_usd == pytest.approx(expected_cost)


def test_creates_forecast_and_stores_it(db, clock):
    svc, claude = make_service(db, clock, [json.dumps(GOOD_RESULT)])
    row = svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD", buy_price=100.0)
    assert row.ticker == "AAPL" and row.horizon_days == 30
    assert row.confidence == "medium"
    assert row.cost_usd > 0
    combined = row.result()
    assert combined["result"]["summary"].startswith("Акция")
    assert "p50" in combined["monte_carlo"]
    assert len(claude.calls) == 1  # с первого раза всё хорошо, повторного запроса не было


def test_cache_hit_returns_without_calling_claude(db, clock):
    svc, claude = make_service(db, clock, [json.dumps(GOOD_RESULT)])
    svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")
    cached = svc.get_cached("AAPL", 30)
    assert cached is not None
    assert len(claude.calls) == 1  # повторного вызова для get_cached не было


def test_cache_expires_after_ttl(db, clock):
    svc, claude = make_service(db, clock, [json.dumps(GOOD_RESULT)])
    svc.ttl = svc.ttl  # оставляем дефолт 86400s
    svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")
    clock.advance(86400 + 1)
    assert svc.get_cached("AAPL", 30) is None


def test_retries_once_when_probabilities_do_not_sum_to_one(db, clock):
    bad = {**GOOD_RESULT, "scenarios": [
        {**GOOD_RESULT["scenarios"][0], "probability": 0.5},
        {**GOOD_RESULT["scenarios"][1], "probability": 0.5},
        {**GOOD_RESULT["scenarios"][2], "probability": 0.5},  # сумма 1.5 — ошибка
    ]}
    svc, claude = make_service(db, clock, [json.dumps(bad), json.dumps(GOOD_RESULT)])
    row = svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")
    assert len(claude.calls) == 2
    assert claude.calls[1][1] is not None  # второй вызов — с уточняющей инструкцией
    assert "вероятност" in claude.calls[1][1].lower()
    combined = row.result()
    assert combined["result"]["confidence"] == "medium"  # взят исправленный (второй) ответ


def test_raises_forecast_error_if_still_bad_after_retry(db, clock):
    bad = {**GOOD_RESULT, "scenarios": [
        {**GOOD_RESULT["scenarios"][0], "probability": 0.9},
        {**GOOD_RESULT["scenarios"][1], "probability": 0.9},
        {**GOOD_RESULT["scenarios"][2], "probability": 0.9},
    ]}
    svc, claude = make_service(db, clock, [json.dumps(bad), json.dumps(bad)])
    with pytest.raises(ForecastError, match="даже после уточнения"):
        svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")
    # Ничего не должно было сохраниться в базу
    assert db.query(Forecast).count() == 0


def test_raises_forecast_error_on_invalid_json(db, clock):
    svc, claude = make_service(db, clock, ["это не json"])
    with pytest.raises(ForecastError):
        svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")


def test_budget_exceeded_blocks_new_forecast(db, clock):
    svc, claude = make_service(db, clock, [json.dumps(GOOD_RESULT)] * 3, monthly_budget=0.0001)
    svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")
    with pytest.raises(BudgetExceededError):
        svc.create_forecast("MSFT", "US", 30, current_price=200.0, currency="USD")


def test_monthly_spend_resets_each_month(db, clock):
    svc, claude = make_service(db, clock, [json.dumps(GOOD_RESULT)])
    svc.create_forecast("AAPL", "US", 30, current_price=105.0, currency="USD")
    spend_before = svc.get_monthly_spend()
    assert spend_before > 0

    from datetime import datetime
    clock.t = datetime(clock.t.year + (1 if clock.t.month == 12 else 0),
                        1 if clock.t.month == 12 else clock.t.month + 1, 1)
    assert svc.get_monthly_spend() == 0.0


def test_not_enough_history_raises_clear_error(db, clock):
    class TinyHistoryProvider:
        def fetch(self, ticker, days):
            return [Candle(date=date.today(), open=100, high=100, low=100, close=100, volume=1)]

    history_service = HistoryService(db, TinyHistoryProvider(), now=clock)
    fundamentals_service = FundamentalsService(db, FakeFundamentalsProvider(), now=clock)
    svc = ForecastService(db, FakeClaude([]), history_service, fundamentals_service, now=clock)
    with pytest.raises(ForecastError, match="Недостаточно истории"):
        svc.create_forecast("NEW", "US", 30, current_price=100.0, currency="USD")
