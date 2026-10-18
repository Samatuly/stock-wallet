from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.accuracy import AccuracyService
from app.services.claude_client import ClaudeClient
from app.services.forecast import ForecastService
from app.services.fundamentals import FundamentalsService, YahooFundamentalsProvider
from app.services.fx import FxService
from app.services.history import HistoryService, YahooHistoryProvider
from app.services.intraday import IntradayService, YahooIntradayProvider
from app.services.long_term import LongTermForecastService
from app.services.quote_provider import FinnhubProvider, QuoteService, YahooProvider


def get_quote_service(db: Session = Depends(get_db)) -> QuoteService:
    settings = get_settings()
    return QuoteService(
        db,
        finnhub=FinnhubProvider(settings.finnhub_api_key),
        yahoo=YahooProvider(),
        ttl_seconds=settings.price_ttl_seconds,
    )


def get_fx_service(db: Session = Depends(get_db)) -> FxService:
    settings = get_settings()
    return FxService(db, ttl_seconds=settings.fx_ttl_seconds)


def get_history_service(db: Session = Depends(get_db)) -> HistoryService:
    settings = get_settings()
    return HistoryService(db, YahooHistoryProvider(), ttl_seconds=settings.history_ttl_seconds)


def get_intraday_service() -> IntradayService:
    return IntradayService(YahooIntradayProvider())


def get_fundamentals_service(db: Session = Depends(get_db)) -> FundamentalsService:
    settings = get_settings()
    return FundamentalsService(
        db, YahooFundamentalsProvider(), ttl_seconds=settings.fundamentals_ttl_seconds
    )


def get_forecast_service(
    db: Session = Depends(get_db),
    history_service: HistoryService = Depends(get_history_service),
    fundamentals_service: FundamentalsService = Depends(get_fundamentals_service),
) -> ForecastService:
    settings = get_settings()
    claude = ClaudeClient(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
    )
    return ForecastService(
        db, claude, history_service, fundamentals_service,
        ttl_seconds=settings.forecast_ttl_seconds,
        monthly_budget_usd=settings.forecast_monthly_budget_usd,
        monte_carlo_paths=settings.monte_carlo_paths,
    )


def get_long_term_service(
    db: Session = Depends(get_db),
    history_service: HistoryService = Depends(get_history_service),
    fundamentals_service: FundamentalsService = Depends(get_fundamentals_service),
    forecast_service: ForecastService = Depends(get_forecast_service),
) -> LongTermForecastService:
    settings = get_settings()
    return LongTermForecastService(
        db, forecast_service.claude, history_service, fundamentals_service,
        budget_service=forecast_service,
        ttl_seconds=settings.long_term_forecast_ttl_seconds,
    )


def get_accuracy_service(
    db: Session = Depends(get_db),
    history_service: HistoryService = Depends(get_history_service),
) -> AccuracyService:
    return AccuracyService(db, history_service)
