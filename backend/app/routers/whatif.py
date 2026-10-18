from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_fx_service, get_quote_service
from app.models import Position
from app.schemas import WhatIfRequest, WhatIfResult
from app.services.fx import FxService
from app.services.portfolio import build_portfolio
from app.services.quote_provider import QuoteService
from app.services.whatif import simulate_what_if

router = APIRouter(tags=["whatif"])


@router.post("/whatif", response_model=WhatIfResult)
def what_if(
    body: WhatIfRequest,
    db: Session = Depends(get_db),
    quotes: QuoteService = Depends(get_quote_service),
    fx: FxService = Depends(get_fx_service),
):
    positions = list(db.scalars(select(Position).order_by(Position.ticker, Position.buy_date)).all())
    valued = build_portfolio(positions, quotes.get_quotes([(p.ticker, p.market) for p in positions]))
    currencies = {p.currency for p in valued.positions} | {body.display_currency}
    table = fx.get_rates(currencies)
    return simulate_what_if(valued.positions, body, table)
