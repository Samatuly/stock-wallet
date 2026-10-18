from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_fx_service, get_history_service, get_quote_service
from app.models import Position
from app.schemas import DashboardOut
from app.services.benchmark import BENCHMARK_TICKER, build_benchmark_comparison
from app.services.dashboard import build_dashboard
from app.services.fx import FxService
from app.services.history import HistoryService
from app.services.quote_provider import QuoteService

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(
    display_currency: str = Query("USD", min_length=3, max_length=3),
    db: Session = Depends(get_db),
    quotes_service: QuoteService = Depends(get_quote_service),
    fx: FxService = Depends(get_fx_service),
    history_service: HistoryService = Depends(get_history_service),
):
    positions = db.scalars(select(Position).order_by(Position.ticker, Position.buy_date)).all()
    quotes = quotes_service.get_quotes([(p.ticker, p.market) for p in positions])

    display_currency = display_currency.upper()
    currencies_used = {p.currency for p in positions}
    table = fx.get_rates(currencies_used | {display_currency})

    # История нужна только для волатильности; берём из кэша (force=False), чтобы
    # открытие дашборда не вызывало лишних запросов к yfinance.
    history = {p.ticker: history_service.get_history(p.ticker, days=180) for p in positions}

    benchmark = None
    if positions:
        oldest = min(p.buy_date for p in positions)
        days_needed = min((date.today() - oldest).days + 10, 3650)
        bench_rows = history_service.get_history(BENCHMARK_TICKER, days=days_needed)
        benchmark = build_benchmark_comparison(
            list(positions), quotes, table, display_currency, bench_rows
        )

    return build_dashboard(list(positions), quotes, table, display_currency, history, benchmark)
