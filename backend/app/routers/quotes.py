from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_fundamentals_service, get_history_service, get_quote_service
from app.models import ManualPrice, utcnow
from app.schemas import FundamentalsOut, HistoryPoint, IndicatorSeries, ManualPriceIn, Market, QuoteOut
from app.services.fundamentals import FundamentalsService
from app.services.history import HistoryService
from app.services.indicators import macd as compute_macd
from app.services.indicators import rsi as compute_rsi
from app.services.indicators import sma as compute_sma
from app.services.quote_provider import QuoteService

router = APIRouter(tags=["quotes"])


@router.get("/quotes/{ticker}", response_model=QuoteOut)
def get_quote(
    ticker: str,
    market: Market = "US",
    refresh: bool = Query(False, description="Игнорировать кэш"),
    service: QuoteService = Depends(get_quote_service),
):
    quote = service.get_quote(ticker, market, force=refresh)
    if quote is None:
        raise HTTPException(status_code=404, detail="Цена не найдена: задайте её вручную")
    return QuoteOut(**quote.__dict__)


@router.get("/quotes/{ticker}/history", response_model=list[HistoryPoint])
def get_history(
    ticker: str,
    days: int = Query(365, ge=5, le=3650, description="Сколько дней истории показать"),
    refresh: bool = Query(False, description="Игнорировать кэш"),
    service: HistoryService = Depends(get_history_service),
):
    return service.get_history(ticker, days=days, force=refresh)


@router.get("/quotes/{ticker}/indicators", response_model=IndicatorSeries)
def get_indicators(
    ticker: str,
    days: int = Query(220, ge=60, le=3650, description="Сколько дней истории использовать"),
    refresh: bool = Query(False, description="Игнорировать кэш"),
    service: HistoryService = Depends(get_history_service),
):
    rows = service.get_history(ticker, days=days, force=refresh)
    closes = [r.close for r in rows]
    macd_line, macd_signal, macd_hist = compute_macd(closes)
    return IndicatorSeries(
        dates=[r.date for r in rows],
        close=closes,
        sma_20=compute_sma(closes, 20),
        sma_50=compute_sma(closes, 50),
        rsi_14=compute_rsi(closes, 14),
        macd=macd_line,
        macd_signal=macd_signal,
        macd_histogram=macd_hist,
    )


@router.get("/quotes/{ticker}/fundamentals", response_model=FundamentalsOut)
def get_fundamentals(
    ticker: str,
    refresh: bool = Query(False, description="Игнорировать кэш"),
    service: FundamentalsService = Depends(get_fundamentals_service),
):
    result = service.get(ticker, force=refresh)
    return FundamentalsOut(**result.__dict__)


@router.put("/manual-prices", response_model=QuoteOut)
def set_manual_price(data: ManualPriceIn, db: Session = Depends(get_db)):
    row = ManualPrice(
        ticker=data.ticker, price=data.price, currency=data.currency, updated_at=utcnow()
    )
    db.merge(row)
    db.commit()
    return QuoteOut(
        ticker=row.ticker,
        price=row.price,
        currency=row.currency,
        source="manual",
        fetched_at=row.updated_at,
        is_manual=True,
    )


@router.delete("/manual-prices/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def delete_manual_price(ticker: str, db: Session = Depends(get_db)):
    row = db.get(ManualPrice, ticker.upper())
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
