"""Оркестратор краткосрочного прогноза: собирает данные, считает Monte Carlo,
отправляет пакет в Claude, проверяет и сохраняет ответ.

Порядок (как в документе проекта):
1. Проверить кэш — если есть прогноз моложе 24 часов на этот тикер и горизонт,
   вернуть его и не тратить деньги на Claude повторно.
2. Проверить месячный бюджет — если лимит исчерпан, отказать до начала счёта.
3. Собрать историю цены, индикаторы, фундаментал, текущую цену.
4. Посчитать Monte Carlo (чистая математика, без Claude).
5. Отправить всё в Claude с инструкцией вернуть строго JSON по схеме.
6. Проверить ответ: валидный JSON, сумма вероятностей сценариев ≈ 1. Если нет —
   один повторный запрос с уточнением, иначе явная ошибка (не сохраняем мусор).
7. Сохранить в базу вместе с стоимостью вызова, вернуть результат.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Forecast, LongTermForecast, utcnow
from app.schemas import ForecastResult
from app.services.claude_client import ClaudeClient, ClaudeError, ClaudeTruncatedError, parse_json_response
from app.services.fundamentals import Fundamentals, FundamentalsService
from app.services.history import HistoryService
from app.services.indicators import macd, rsi, sma
from app.services.monte_carlo import MonteCarloResult, estimate_mu_sigma, simulate

log = logging.getLogger(__name__)

PROBABILITY_SUM_TOLERANCE = 0.03


class ForecastError(Exception):
    """Не удалось построить прогноз (нет данных, Claude вернул мусор, бюджет исчерпан)."""


class BudgetExceededError(ForecastError):
    pass


def _last_not_none(values: list) -> Optional[float]:
    for v in reversed(values):
        if v is not None:
            return v
    return None


def build_data_package(
    ticker: str,
    horizon_days: int,
    current_price: float,
    currency: str,
    buy_price: Optional[float],
    closes: list[float],
    mc: MonteCarloResult,
    fundamentals: Fundamentals,
) -> str:
    """Собирает всё в компактный JSON-пакет, который видит Claude. Текстом, а не
    объектами Python — так его проще логировать и проверять вручную при отладке."""
    sma20 = _last_not_none(sma(closes, 20))
    sma50 = _last_not_none(sma(closes, 50))
    rsi14 = _last_not_none(rsi(closes, 14))
    macd_line, macd_signal, _ = macd(closes)
    macd_last = _last_not_none(macd_line)
    macd_signal_last = _last_not_none(macd_signal)

    package = {
        "ticker": ticker,
        "horizon_days": horizon_days,
        "currency": currency,
        "current_price": round(current_price, 4),
        "buy_price": round(buy_price, 4) if buy_price is not None else None,
        "monte_carlo": {
            "p10": mc.p10, "p50": mc.p50, "p90": mc.p90,
            "prob_above_buy_price": mc.prob_above_buy_price,
            "paths": mc.paths,
            "assumed_annual_drift": mc.mu_annual,
            "assumed_annual_volatility": mc.sigma_annual,
            "note": "дрейф и волатильность оценены по истории цены — не гарантия будущего",
        },
        "indicators": {
            "sma_20": round(sma20, 4) if sma20 is not None else None,
            "sma_50": round(sma50, 4) if sma50 is not None else None,
            "rsi_14": round(rsi14, 2) if rsi14 is not None else None,
            "macd": round(macd_last, 4) if macd_last is not None else None,
            "macd_signal": round(macd_signal_last, 4) if macd_signal_last is not None else None,
        },
        "fundamentals": {
            "pe_ratio": fundamentals.pe_ratio,
            "dividend_yield_percent": fundamentals.dividend_yield,
            "next_earnings_date": str(fundamentals.next_earnings_date) if fundamentals.next_earnings_date else None,
            "is_stale": fundamentals.is_stale,
        },
        "history_points_available": len(closes),
    }
    return json.dumps(package, ensure_ascii=False)


def _validate_result(result: ForecastResult) -> Optional[str]:
    """Возвращает текст проблемы, если ответ не проходит проверку, иначе None."""
    if len(result.scenarios) != 3:
        return "Должно быть ровно три сценария: optimistic, base, pessimistic."
    names = {s.name for s in result.scenarios}
    if names != {"optimistic", "base", "pessimistic"}:
        return "Сценарии должны называться ровно optimistic, base, pessimistic."
    total = sum(s.probability for s in result.scenarios)
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
        return f"Сумма вероятностей сценариев должна быть равна 1.0, а получилось {total:.3f}."
    return None


@dataclass
class ForecastBundle:
    monte_carlo: MonteCarloResult
    result: ForecastResult
    price_at_forecast: float
    currency: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class ForecastService:
    def __init__(
        self,
        db: Session,
        claude: ClaudeClient,
        history_service: HistoryService,
        fundamentals_service: FundamentalsService,
        ttl_seconds: int = 86400,
        monthly_budget_usd: float = 10.0,
        monte_carlo_paths: int = 5000,
        now: Callable[[], datetime] = utcnow,
    ):
        self.db = db
        self.claude = claude
        self.history_service = history_service
        self.fundamentals_service = fundamentals_service
        self.ttl = timedelta(seconds=ttl_seconds)
        self.monthly_budget_usd = monthly_budget_usd
        self.monte_carlo_paths = monte_carlo_paths
        self.now = now

    def get_monthly_spend(self) -> float:
        month_start = self.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        short = self.db.scalar(
            select(func.sum(Forecast.cost_usd)).where(Forecast.created_at >= month_start)
        )
        long_ = self.db.scalar(
            select(func.sum(LongTermForecast.cost_usd)).where(LongTermForecast.created_at >= month_start)
        )
        return round((short or 0.0) + (long_ or 0.0), 4)

    def get_cached(self, ticker: str, horizon_days: int) -> Optional[Forecast]:
        row = self.db.scalar(
            select(Forecast)
            .where(Forecast.ticker == ticker.upper(), Forecast.horizon_days == horizon_days)
            .order_by(Forecast.created_at.desc())
        )
        if row and self.now() - row.created_at < self.ttl:
            return row
        return None

    def _call_claude_and_validate(self, package: str) -> tuple[ForecastResult, int, int]:
        extra_input_tokens = extra_output_tokens = 0
        try:
            response = self.claude.complete_json(package)
        except ClaudeTruncatedError as exc:
            # Не хватило места на полный ответ (например, расширенное мышление
            # само съело часть лимита) — пробуем один раз с удвоенным бюджетом,
            # а не сразу сдаёмся. Это проблема места, а не содержания, поэтому
            # без уточняющей инструкции — просто тот же запрос ещё раз. Токены
            # неудачной попытки всё равно были потрачены и оплачены — считаем их.
            log.warning("Ответ Claude оборвался по max_tokens, повторяю с удвоенным лимитом")
            extra_input_tokens, extra_output_tokens = exc.input_tokens, exc.output_tokens
            response = self.claude.complete_json(
                package, max_tokens_override=self.claude.max_tokens * 2
            )
        raw = parse_json_response(response.text)
        try:
            result = ForecastResult.model_validate(raw)
        except Exception as exc:  # pydantic ValidationError и прочее
            raise ForecastError(f"Ответ Claude не соответствует схеме: {exc}") from exc

        problem = _validate_result(result)
        if problem is None:
            return (
                result,
                extra_input_tokens + response.input_tokens,
                extra_output_tokens + response.output_tokens,
            )

        log.warning("Ответ Claude не прошёл проверку, пробуем один раз уточнить: %s", problem)
        retry = self.claude.complete_json(
            package,
            extra_instruction=f"{problem} Верни исправленный JSON целиком, строго по той же схеме.",
            previous_response_text=response.text,
        )
        raw2 = parse_json_response(retry.text)
        result2 = ForecastResult.model_validate(raw2)
        problem2 = _validate_result(result2)
        if problem2 is not None:
            raise ForecastError(f"Claude не смог дать корректный ответ даже после уточнения: {problem2}")
        total_input = extra_input_tokens + response.input_tokens + retry.input_tokens
        total_output = extra_output_tokens + response.output_tokens + retry.output_tokens
        return result2, total_input, total_output

    def create_forecast(
        self,
        ticker: str,
        market: str,
        horizon_days: int,
        current_price: float,
        currency: str,
        buy_price: Optional[float] = None,
    ) -> Forecast:
        if self.get_monthly_spend() >= self.monthly_budget_usd:
            raise BudgetExceededError(
                f"Месячный лимит расходов на Claude (${self.monthly_budget_usd:.2f}) исчерпан. "
                "Увеличьте лимит в настройках или дождитесь следующего месяца."
            )

        history = self.history_service.get_history(ticker, days=400)
        closes = [h.close for h in history]
        if len(closes) < 30:
            raise ForecastError(
                f"Недостаточно истории цены для прогноза ({len(closes)} точек, нужно хотя бы 30)."
            )

        fundamentals = self.fundamentals_service.get(ticker)
        mu, sigma = estimate_mu_sigma(closes)
        mc = simulate(
            current_price=current_price, mu_annual=mu, sigma_annual=sigma,
            horizon_days=horizon_days, buy_price=buy_price, n_paths=self.monte_carlo_paths,
        )
        package = build_data_package(
            ticker, horizon_days, current_price, currency, buy_price, closes, mc, fundamentals
        )

        try:
            result, input_tokens, output_tokens = self._call_claude_and_validate(package)
        except ClaudeError as exc:
            raise ForecastError(str(exc)) from exc

        cost = round(
            input_tokens / 1_000_000 * 2.0 + output_tokens / 1_000_000 * 10.0, 6
        )
        # Храним Monte Carlo и ответ Claude вместе одним JSON: кэшированный прогноз
        # должен отдавать и то, и другое, не пересчитывая Monte Carlo заново.
        combined = {
            "monte_carlo": {
                "p10": mc.p10, "p50": mc.p50, "p90": mc.p90,
                "prob_above_buy_price": mc.prob_above_buy_price,
                "paths": mc.paths, "mu_annual": mc.mu_annual, "sigma_annual": mc.sigma_annual,
            },
            "result": result.model_dump(),
        }
        row = Forecast(
            ticker=ticker.upper(), market=market, horizon_days=horizon_days,
            created_at=self.now(), price_at_forecast=current_price, currency=currency,
            result_json=json.dumps(combined, ensure_ascii=False), confidence=result.confidence,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
