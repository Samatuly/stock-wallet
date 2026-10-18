from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import (
    get_accuracy_service,
    get_forecast_service,
    get_long_term_service,
    get_quote_service,
)
from app.models import Forecast, Position
from app.schemas import (
    BudgetStatus,
    ForecastAccuracySummary,
    ForecastOut,
    ForecastRequest,
    ForecastResult,
    LongTermForecastOut,
    LongTermForecastRequest,
    MonteCarloOut,
)
from app.services.accuracy import AccuracyService
from app.services.long_term import LongTermForecastService, build_output
from app.services.forecast import BudgetExceededError, ForecastError, ForecastService
from app.services.quote_provider import QuoteService

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


def _to_out(row: Forecast, from_cache: bool) -> ForecastOut:
    combined = row.result()
    return ForecastOut(
        ticker=row.ticker,
        horizon_days=row.horizon_days,
        created_at=row.created_at,
        price_at_forecast=row.price_at_forecast,
        currency=row.currency,
        monte_carlo=MonteCarloOut(**combined["monte_carlo"]),
        result=ForecastResult.model_validate(combined["result"]),
        cost_usd=row.cost_usd,
        from_cache=from_cache,
    )


@router.post("/{ticker}", response_model=ForecastOut)
def create_forecast(
    ticker: str,
    body: ForecastRequest,
    db: Session = Depends(get_db),
    quotes_service: QuoteService = Depends(get_quote_service),
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    ticker = ticker.upper()

    if not body.refresh:
        cached = forecast_service.get_cached(ticker, body.horizon_days)
        if cached:
            return _to_out(cached, from_cache=True)

    # Рынок определяем по уже сохранённой позиции с этим тикером, если есть,
    # иначе считаем, что это США (по умолчанию для котировок без рынка).
    position = db.scalar(select(Position).where(Position.ticker == ticker))
    market = position.market if position else "US"
    currency = position.currency if position else "USD"

    quote = quotes_service.get_quote(ticker, market)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"Нет текущей цены для {ticker}, прогноз невозможен")

    try:
        row = forecast_service.create_forecast(
            ticker=ticker, market=market, horizon_days=body.horizon_days,
            current_price=quote.price, currency=currency, buy_price=body.buy_price,
        )
    except BudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ForecastError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _to_out(row, from_cache=False)


@router.get("/_budget/status", response_model=BudgetStatus)
def get_budget_status(forecast_service: ForecastService = Depends(get_forecast_service)):
    spent = forecast_service.get_monthly_spend()
    limit = forecast_service.monthly_budget_usd
    return BudgetStatus(
        month=forecast_service.now().strftime("%Y-%m"),
        spent_usd=spent,
        limit_usd=limit,
        remaining_usd=round(max(limit - spent, 0), 4),
        is_over_limit=spent >= limit,
    )


@router.get("/accuracy", response_model=ForecastAccuracySummary)
def get_accuracy(service: AccuracyService = Depends(get_accuracy_service)):
    """Сравнение прошлых прогнозов с фактическими ценами. Должен идти ДО /{ticker}."""
    return service.summary()


@router.get("/{ticker}", response_model=ForecastOut | None)
def get_last_forecast(
    ticker: str,
    horizon_days: int = Query(30),
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    cached = forecast_service.get_cached(ticker.upper(), horizon_days)
    if cached is None:
        return None
    return _to_out(cached, from_cache=True)




@router.get("/{ticker}/long-term", response_model=LongTermForecastOut | None)
def get_long_term(ticker: str, service: LongTermForecastService = Depends(get_long_term_service)):
    cached = service.get_cached(ticker.upper())
    return build_output(cached, from_cache=True) if cached else None


@router.post("/{ticker}/long-term", response_model=LongTermForecastOut)
def create_long_term(
    ticker: str,
    body: LongTermForecastRequest,
    db: Session = Depends(get_db),
    quotes_service: QuoteService = Depends(get_quote_service),
    service: LongTermForecastService = Depends(get_long_term_service),
):
    ticker = ticker.upper()
    if not body.refresh:
        cached = service.get_cached(ticker)
        if cached:
            return build_output(cached, from_cache=True)

    position = db.scalar(select(Position).where(Position.ticker == ticker))
    market = position.market if position else "US"
    currency = position.currency if position else "USD"

    quote = quotes_service.get_quote(ticker, market)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"Нет текущей цены для {ticker}, прогноз невозможен")

    try:
        row = service.create(ticker, market, quote.price, currency)
    except BudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ForecastError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return build_output(row, from_cache=False)
