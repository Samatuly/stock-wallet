from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_fx_service, get_quote_service
from app.models import Position
from app.schemas import PortfolioOut
from app.services.fx import FxService
from app.services.portfolio import build_portfolio, combine_totals
from app.services.quote_provider import QuoteService

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=PortfolioOut)
def get_portfolio(
    refresh: bool = Query(False, description="Запросить свежие цены, минуя кэш"),
    display_currency: str = Query(
        "USD", min_length=3, max_length=3, description="В какой валюте показать общий итог"
    ),
    db: Session = Depends(get_db),
    service: QuoteService = Depends(get_quote_service),
    fx: FxService = Depends(get_fx_service),
):
    positions = db.scalars(select(Position).order_by(Position.ticker, Position.buy_date)).all()
    quotes = service.get_quotes([(p.ticker, p.market) for p in positions], force=refresh)
    result = build_portfolio(list(positions), quotes)

    display_currency = display_currency.upper()
    currencies_used = {t.currency for t in result.totals}
    table = fx.get_rates(currencies_used | {display_currency})
    result.combined = combine_totals(result.totals, display_currency, table)
    return result
