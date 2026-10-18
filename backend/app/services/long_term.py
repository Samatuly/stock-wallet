"""Долгосрочный прогноз (1, 5, 10 лет) по методу «кирпичиков доходности».

    1 + R_цены = (1 + g) · (1 + b) · (1 + m) · (P/E_T / P/E_0)^(1/T)
    R_полная  ≈ R_цены + d

g — рост выручки, b — чистый выкуп акций, m — изменение маржи, последний
множитель — изменение оценки (P/E), d — дивидендная доходность. Все параметры
в долях за год.

Разделение труда: Claude предлагает допущения по трём сценариям и объясняет их,
а ЦЕНЫ считает код (compute_scenario). Claude арифметику не делает.

Честная оговорка: банки публикуют такие прогнозы для индексов и классов
активов, а не для отдельных акций. Для одной акции неопределённость заметно
выше; в данных нет выручки и маржи, поэтому допущения Claude приблизительные.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LongTermForecast, utcnow
from app.schemas import (
    LongTermForecastInput,
    LongTermForecastOut,
    LongTermScenarioInput,
    LongTermScenarioOut,
    LongTermScenarioPoint,
)
from app.services.claude_client import ClaudeClient, ClaudeError, ClaudeTruncatedError, parse_json_response
from app.services.forecast import BudgetExceededError, ForecastError, ForecastService
from app.services.fundamentals import FundamentalsService
from app.services.history import HistoryService
from app.services.market_baseline import baseline_for_market

log = logging.getLogger(__name__)

YEARS = (1, 5, 10)
PROBABILITY_SUM_TOLERANCE = 0.03
# Если взвешенная доходность расходится с рыночным ориентиром больше, чем на
# столько п.п. в год, Claude обязан объяснить причину.
BENCHMARK_GAP_PP = 4.0

LONG_TERM_SYSTEM_PROMPT = """Ты — финансовый аналитик, который помогает частному инвестору оценить долгосрочные сценарии по одной акции в стиле «кирпичиков доходности» (как в долгосрочных прогнозах J.P. Morgan).

Доходность цены раскладывается так: (1+g)(1+b)(1+m)(1+v), где за год:
g — рост выручки, b — чистый выкуп акций (отрицательный при допэмиссии), m — изменение маржи, v — изменение оценки (P/E).
Дивиденды код добавляет сам.

Жёсткие правила:
1. Ты не даёшь инвестиционных советов и НЕ считаешь цены — только допущения g, b, m, v по трём сценариям. Цены посчитает код.
2. Все четыре параметра — доли в год (0.05 означает 5% в год). Не процентные числа.
3. Используй только данные из пакета. В пакете нет выручки и маржи компании: опирайся на общие соображения и историческую динамику цены, снижай уверенность и перечисляй это в data_gaps.
4. Допущения должны быть реалистичными для горизонта до 10 лет: устойчивый рост выручки выше 15% в год или смена P/E более чем на 5% в год за десять лет — редкость.
5. Сценарии ровно три: optimistic, base, pessimistic; сумма вероятностей 1.0.
6. В пакете есть ориентир рынка (benchmark_annual_return_percent). Если твой вероятностно-взвешенный годовой результат (с дивидендами) отличается от него больше чем на 4 п.п., ОБЯЗАТЕЛЬНО объясни причину в benchmark_comparison_note.
7. Отвечай СТРОГО JSON по схеме, без текста до или после и без markdown-разметки.

Схема:
{
  "summary": "2-3 предложения простым языком",
  "scenarios": [
    {"name": "optimistic", "probability": 0.0-1.0, "revenue_growth_annual": число, "net_buyback_annual": число, "margin_change_annual": число, "valuation_change_annual": число, "rationale": "1-2 предложения"},
    {"name": "base", ...},
    {"name": "pessimistic", ...}
  ],
  "benchmark_comparison_note": "сравнение с рынком; пояснение расхождения, если оно больше 4 п.п.",
  "confidence": "low" | "medium" | "high",
  "data_gaps": ["чего не хватило"]
}"""


def compute_scenario(
    price: float, s: LongTermScenarioInput, dividend_yield: float
) -> tuple[float, float, list[LongTermScenarioPoint]]:
    """Чистая арифметика. dividend_yield — доля в год (0.005 = 0.5%).

    Возвращает (годовая доходность цены, годовая полная доходность, точки по годам).
    Цена через T лет = price · factor^T; полная доходность накапливается по ставке
    (factor - 1 + d) в год.
    """
    factor = (
        (1 + s.revenue_growth_annual)
        * (1 + s.net_buyback_annual)
        * (1 + s.margin_change_annual)
        * (1 + s.valuation_change_annual)
    )
    annual_price = factor - 1
    annual_total = annual_price + dividend_yield
    points = []
    for t in YEARS:
        total_growth = max(1 + annual_total, 0.0) ** t
        points.append(
            LongTermScenarioPoint(
                years=t,
                price=round(price * factor**t, 4),
                total_return_percent=round((total_growth - 1) * 100, 2),
            )
        )
    return annual_price, annual_total, points


def weighted_annual_total_percent(scenarios: list[LongTermScenarioInput], dividend_yield: float) -> float:
    total = 0.0
    for s in scenarios:
        _, annual_total, _ = compute_scenario(1.0, s, dividend_yield)
        total += s.probability * annual_total
    return round(total * 100, 2)


def validate_input(
    result: LongTermForecastInput, dividend_yield: float, benchmark_percent: float
) -> Optional[str]:
    if len(result.scenarios) != 3 or {s.name for s in result.scenarios} != {"optimistic", "base", "pessimistic"}:
        return "Должно быть ровно три сценария: optimistic, base, pessimistic."
    total = sum(s.probability for s in result.scenarios)
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
        return f"Сумма вероятностей сценариев должна быть равна 1.0, а получилось {total:.3f}."
    gap = weighted_annual_total_percent(result.scenarios, dividend_yield) - benchmark_percent
    if abs(gap) > BENCHMARK_GAP_PP and len(result.benchmark_comparison_note.strip()) < 20:
        return (
            f"Вероятностно-взвешенная годовая доходность отличается от рыночного ориентира "
            f"({benchmark_percent}%) на {gap:+.1f} п.п., это больше {BENCHMARK_GAP_PP} п.п. "
            "Объясни причину в benchmark_comparison_note или пересмотри допущения."
        )
    return None


def build_output(row: LongTermForecast, from_cache: bool) -> LongTermForecastOut:
    stored = row.result()
    claude = LongTermForecastInput.model_validate(stored["claude"])
    d_pct = stored.get("dividend_yield_percent")
    d = (d_pct or 0.0) / 100
    scenarios = []
    for s in claude.scenarios:
        ap, at, points = compute_scenario(row.price_at_forecast, s, d)
        scenarios.append(
            LongTermScenarioOut(
                name=s.name, probability=s.probability, rationale=s.rationale,
                revenue_growth_percent=round(s.revenue_growth_annual * 100, 2),
                net_buyback_percent=round(s.net_buyback_annual * 100, 2),
                margin_change_percent=round(s.margin_change_annual * 100, 2),
                valuation_change_percent=round(s.valuation_change_annual * 100, 2),
                annual_price_return_percent=round(ap * 100, 2),
                annual_total_return_percent=round(at * 100, 2),
                points=points,
            )
        )
    order = {"optimistic": 0, "base": 1, "pessimistic": 2}
    scenarios.sort(key=lambda x: order[x.name])
    return LongTermForecastOut(
        ticker=row.ticker, created_at=row.created_at, price_at_forecast=row.price_at_forecast,
        currency=row.currency, dividend_yield_percent=d_pct, pe_ratio=stored.get("pe_ratio"),
        benchmark_name=stored.get("benchmark_name", row.benchmark_key),
        benchmark_return_percent=row.benchmark_return_percent,
        weighted_base_return_percent=weighted_annual_total_percent(claude.scenarios, d),
        summary=claude.summary, scenarios=scenarios,
        benchmark_comparison_note=claude.benchmark_comparison_note,
        confidence=claude.confidence, data_gaps=claude.data_gaps,
        cost_usd=row.cost_usd, from_cache=from_cache,
    )


class LongTermForecastService:
    def __init__(
        self,
        db: Session,
        claude: ClaudeClient,
        history_service: HistoryService,
        fundamentals_service: FundamentalsService,
        budget_service: ForecastService,
        ttl_seconds: int = 30 * 86400,
        now: Callable[[], datetime] = utcnow,
    ):
        self.db = db
        self.claude = claude
        self.history_service = history_service
        self.fundamentals_service = fundamentals_service
        self.budget_service = budget_service  # общий месячный счётчик расходов
        self.ttl = timedelta(seconds=ttl_seconds)
        self.now = now

    def get_cached(self, ticker: str) -> Optional[LongTermForecast]:
        row = self.db.scalar(
            select(LongTermForecast)
            .where(LongTermForecast.ticker == ticker.upper())
            .order_by(LongTermForecast.created_at.desc())
        )
        if row and self.now() - row.created_at < self.ttl:
            return row
        return None

    def _ask(self, package: str, extra: Optional[str] = None, previous: Optional[str] = None):
        """Один вызов Claude; при обрыве по max_tokens — одна повторная попытка.
        Возвращает (ответ, суммарные входные токены, суммарные выходные токены)."""
        in_t = out_t = 0
        try:
            resp = self.claude.complete_json(
                package, extra_instruction=extra, previous_response_text=previous,
                system_prompt=LONG_TERM_SYSTEM_PROMPT,
            )
        except ClaudeTruncatedError as exc:
            in_t, out_t = exc.input_tokens, exc.output_tokens
            resp = self.claude.complete_json(
                package, extra_instruction=extra, previous_response_text=previous,
                max_tokens_override=self.claude.max_tokens * 2,
                system_prompt=LONG_TERM_SYSTEM_PROMPT,
            )
        return resp, in_t + resp.input_tokens, out_t + resp.output_tokens

    def _parse(self, text: str) -> LongTermForecastInput:
        raw = parse_json_response(text)
        try:
            return LongTermForecastInput.model_validate(raw)
        except Exception as exc:
            raise ForecastError(f"Ответ Claude не соответствует схеме: {exc}") from exc

    def _ask_and_validate(self, package: str, d: float, bench: float):
        resp, in_t, out_t = self._ask(package)
        problem = None
        try:
            result = self._parse(resp.text)
            problem = validate_input(result, d, bench)
        except ForecastError as exc:
            problem = str(exc)
        if problem is None:
            return result, in_t, out_t

        log.warning("Долгосрочный ответ не прошёл проверку, уточняем: %s", problem)
        resp2, in2, out2 = self._ask(
            package,
            extra=f"{problem} Верни исправленный JSON целиком, строго по той же схеме.",
            previous=resp.text,
        )
        result2 = self._parse(resp2.text)
        problem2 = validate_input(result2, d, bench)
        if problem2 is not None:
            raise ForecastError(f"Claude не смог дать корректный ответ даже после уточнения: {problem2}")
        return result2, in_t + in2, out_t + out2

    def create(
        self, ticker: str, market: str, current_price: float, currency: str
    ) -> LongTermForecast:
        ticker = ticker.upper()
        if self.budget_service.get_monthly_spend() >= self.budget_service.monthly_budget_usd:
            raise BudgetExceededError(
                f"Месячный лимит расходов на Claude (${self.budget_service.monthly_budget_usd:.2f}) исчерпан."
            )

        baseline = baseline_for_market(market)
        fundamentals = self.fundamentals_service.get(ticker)
        d_pct = fundamentals.dividend_yield
        d = (d_pct or 0.0) / 100

        # История для справки: чему равна среднегодовая динамика цены за доступный период.
        hist_info: dict = {"years_covered": None, "price_cagr_percent": None}
        try:
            history = self.history_service.get_history(ticker, days=1800)
            if len(history) >= 250:
                span_years = (history[-1].date - history[0].date).days / 365.25
                if span_years >= 1 and history[0].close > 0:
                    cagr = (history[-1].close / history[0].close) ** (1 / span_years) - 1
                    hist_info = {"years_covered": round(span_years, 1), "price_cagr_percent": round(cagr * 100, 2)}
        except Exception as exc:  # история — лишь справка, прогноз без неё возможен
            log.warning("История для долгосрочного прогноза %s недоступна: %s", ticker, exc)

        package = json.dumps(
            {
                "ticker": ticker,
                "market": market,
                "currency": currency,
                "current_price": round(current_price, 4),
                "pe_ratio": fundamentals.pe_ratio,
                "dividend_yield_percent": d_pct,
                "historical_price_dynamics": hist_info,
                "benchmark_name": baseline.name,
                "benchmark_annual_return_percent": baseline.annual_return_percent,
                "revenue_and_margin_data_available": False,
                "horizons_years": list(YEARS),
            },
            ensure_ascii=False,
        )

        try:
            result, in_t, out_t = self._ask_and_validate(package, d, baseline.annual_return_percent)
        except ClaudeError as exc:
            raise ForecastError(str(exc)) from exc

        cost = round(in_t / 1_000_000 * 2.0 + out_t / 1_000_000 * 10.0, 6)
        stored = {
            "claude": result.model_dump(),
            "dividend_yield_percent": d_pct,
            "pe_ratio": fundamentals.pe_ratio,
            "benchmark_name": baseline.name,
        }
        row = LongTermForecast(
            ticker=ticker, market=market, created_at=self.now(), price_at_forecast=current_price,
            currency=currency, benchmark_key=baseline.key,
            benchmark_return_percent=baseline.annual_return_percent,
            result_json=json.dumps(stored, ensure_ascii=False), confidence=result.confidence,
            input_tokens=in_t, output_tokens=out_t, cost_usd=cost,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
