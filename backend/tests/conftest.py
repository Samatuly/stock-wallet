from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import get_forecast_service, get_fx_service, get_history_service, get_quote_service
from app.main import app
from app.services.forecast import ForecastService
from app.services.fundamentals import FundamentalsService
from app.services.fx import FxService
from app.services.history import Candle, HistoryService
from app.services.quote_provider import QuoteProviderError, QuoteService


class FakeProvider:
    """Поддельный источник цен: ничего не запрашивает в интернете."""

    def __init__(self, name, prices=None, fail=False):
        self.name = name
        self.prices = prices or {}
        self.fail = fail
        self.calls = []

    def fetch(self, ticker):
        self.calls.append(ticker)
        if self.fail or ticker not in self.prices:
            raise QuoteProviderError(f"{self.name}: нет данных")
        return self.prices[ticker]


class Clock:
    """Управляемые часы для проверки срока жизни кэша."""

    def __init__(self):
        self.t = datetime(2026, 9, 28, 12, 0, 0)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def client(db, clock):
    finnhub = FakeProvider("finnhub", {"AAPL": (195.20, "USD")})
    yahoo = FakeProvider("yfinance", {"SAP.DE": (150.0, "EUR")})

    def fake_fx_get(url, params=None, timeout=None, follow_redirects=False):
        # Формат v2 Frankfurter: плоский список {date, base, quote, rate}
        class Resp:
            def raise_for_status(self_):
                pass

            def json(self_):
                table = {"EUR": 0.92, "KZT": 470.5, "GBP": 0.79}
                return [
                    {"date": "2026-09-28", "base": "USD", "quote": c, "rate": table.get(c, 1.0)}
                    for c in params["quotes"].split(",")
                ]

        return Resp()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_quote_service] = lambda: QuoteService(
        db, finnhub, yahoo, ttl_seconds=300, now=clock
    )
    app.dependency_overrides[get_fx_service] = lambda: FxService(
        db, http_get=fake_fx_get, now=clock
    )

    class FakeHistoryProvider:
        def fetch(self_, ticker, days):
            from datetime import timedelta

            end = clock().date()
            return [
                Candle(date=end - timedelta(days=i), open=100 - i, high=101 - i,
                       low=99 - i, close=100 - i, volume=1000)
                for i in range(3, 0, -1)
            ]

    app.dependency_overrides[get_history_service] = lambda: HistoryService(
        db, FakeHistoryProvider(), now=clock
    )

    class FakeFundamentalsProviderForForecast:
        def fetch(self_, ticker):
            return {"trailingPE": 20.0}

    GOOD_FORECAST_RESULT = {
        "summary": "Тестовый прогноз.",
        "scenarios": [
            {"name": "optimistic", "probability": 0.25, "price_low": 110, "price_high": 120, "drivers": ["рост"]},
            {"name": "base", "probability": 0.5, "price_low": 100, "price_high": 110, "drivers": ["нейтрально"]},
            {"name": "pessimistic", "probability": 0.25, "price_low": 90, "price_high": 100, "drivers": ["риск"]},
        ],
        "prob_above_buy_price": 0.6,
        "key_risks": ["тестовый риск"],
        "confidence": "medium",
        "data_gaps": [],
    }

    class FakeClaudeForTests:
        def complete_json(self_, package, extra_instruction=None, previous_response_text=None, max_tokens_override=None, system_prompt=None):
            import json as _json

            class R:
                text = _json.dumps(GOOD_FORECAST_RESULT)
                input_tokens = 500
                output_tokens = 200

            return R()

    app.dependency_overrides[get_forecast_service] = lambda: ForecastService(
        db,
        FakeClaudeForTests(),
        HistoryService(db, FakeHistoryProvider(), now=clock),
        FundamentalsService(db, FakeFundamentalsProviderForForecast(), now=clock),
        now=clock,
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
