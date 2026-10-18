"""Точность прогнозов: что предсказывали и что получилось на самом деле.

Прогноз «созревает» через horizon_days после создания. Тогда по истории цены
берём последнюю цену закрытия на эту дату или раньше и сохраняем как actual_price.
Сравниваем: попала ли фактическая цена в диапазон базового сценария, насколько
она отличается от медианы Monte Carlo — и от наивного прогноза «цена не изменится».
Если Claude и Monte Carlo не бьют наивный прогноз, значит прогнозам пока рано верить.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Forecast, utcnow
from app.schemas import ForecastAccuracyItem, ForecastAccuracySummary
from app.services.history import HistoryService

log = logging.getLogger(__name__)

# Если ближайшая известная цена старше срока больше, чем на столько дней
# (выходные и праздники), считаем, что данных за дату нет, и ждём.
MAX_GAP_DAYS = 5


def due_date_of(row: Forecast) -> date:
    return (row.created_at + timedelta(days=row.horizon_days)).date()


def _mean(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


class AccuracyService:
    def __init__(self, db: Session, history_service: HistoryService, now: Callable[[], datetime] = utcnow):
        self.db = db
        self.history_service = history_service
        self.now = now

    def _fill_actual_prices(self) -> None:
        today = self.now().date()
        rows = self.db.scalars(select(Forecast).where(Forecast.actual_price.is_(None))).all()
        changed = False
        for row in rows:
            due = due_date_of(row)
            if due > today:
                continue
            days = (today - row.created_at.date()).days + 10
            try:
                history = self.history_service.get_history(row.ticker, days=days)
            except Exception as exc:
                log.warning("История %s недоступна для оценки точности: %s", row.ticker, exc)
                continue
            before = [h for h in history if h.date <= due]
            if not before:
                continue
            last = before[-1]
            if (due - last.date).days > MAX_GAP_DAYS:
                continue
            row.actual_price = last.close
            changed = True
        if changed:
            self.db.commit()

    def summary(self) -> ForecastAccuracySummary:
        self._fill_actual_prices()
        rows = self.db.scalars(select(Forecast).order_by(Forecast.created_at.desc())).all()
        items: list[ForecastAccuracyItem] = []
        hits: list[bool] = []
        mc_errors: list[float] = []
        naive_errors: list[float] = []

        for row in rows:
            combined = row.result()
            base = next((s for s in combined["result"]["scenarios"] if s["name"] == "base"), None)
            p50 = combined["monte_carlo"]["p50"]
            actual = row.actual_price
            item = ForecastAccuracyItem(
                ticker=row.ticker, horizon_days=row.horizon_days, created_at=row.created_at,
                due_date=due_date_of(row), price_at_forecast=row.price_at_forecast,
                actual_price=actual,
                base_price_low=base["price_low"] if base else None,
                base_price_high=base["price_high"] if base else None,
                monte_carlo_p50=p50,
            )
            if actual is not None:
                if base:
                    item.hit_base_range = base["price_low"] <= actual <= base["price_high"]
                    hits.append(item.hit_base_range)
                if p50:
                    item.pct_error_vs_monte_carlo_p50 = round((actual - p50) / p50 * 100, 2)
                    mc_errors.append(abs(item.pct_error_vs_monte_carlo_p50))
                if row.price_at_forecast:
                    item.pct_error_naive = round((actual - row.price_at_forecast) / row.price_at_forecast * 100, 2)
                    naive_errors.append(abs(item.pct_error_naive))
            items.append(item)

        evaluated = sum(1 for i in items if i.actual_price is not None)
        return ForecastAccuracySummary(
            total_evaluated=evaluated,
            total_pending=len(items) - evaluated,
            hit_rate_base_range_percent=round(sum(hits) / len(hits) * 100, 1) if hits else None,
            mean_abs_pct_error_vs_monte_carlo_p50=_mean(mc_errors),
            mean_abs_pct_error_naive=_mean(naive_errors),
            items=items,
        )
