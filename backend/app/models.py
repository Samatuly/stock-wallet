from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    """Текущее время UTC без часового пояса (так его хранит SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Position(Base):
    """Одна покупка. Несколько покупок одной акции это несколько записей."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(2), default="US")  # US, EU, KZ
    quantity: Mapped[float] = mapped_column(Float)
    buy_price: Mapped[float] = mapped_column(Float)
    buy_date: Mapped[date] = mapped_column(Date)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PriceCache(Base):
    """Последняя цена, полученная от источника (для экономии лимитов API)."""

    __tablename__ = "price_cache"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class FxRate(Base):
    """Курсы валют относительно USD (источник: Frankfurter). Обновляются раз в сутки."""

    __tablename__ = "fx_rates"

    base: Mapped[str] = mapped_column(String(8), primary_key=True)  # всегда "USD"
    rates_json: Mapped[str] = mapped_column(String(4000))
    as_of: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)

    def rates(self) -> dict[str, float]:
        import json

        return json.loads(self.rates_json)


class PriceHistory(Base):
    """Дневная история цены (свечи) для графика на карточке акции."""

    __tablename__ = "price_history"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class FundamentalsCache(Base):
    """Базовые фундаментальные метрики: P/E, дивидендная доходность, дата отчёта."""

    __tablename__ = "fundamentals_cache"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)  # в процентах
    next_earnings_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class Forecast(Base):
    """Сохранённый прогноз Claude по одной акции на определённый горизонт."""

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(2))
    horizon_days: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    price_at_forecast: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    result_json: Mapped[str] = mapped_column(String(8000))
    confidence: Mapped[str] = mapped_column(String(16))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    # Фактическая цена на дату, когда прогноз «созрел» (created_at + horizon_days).
    # Заполняется автоматически на экране «Точность прогнозов».
    actual_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    def result(self) -> dict:
        import json

        return json.loads(self.result_json)


class LongTermForecast(Base):
    """Долгосрочный прогноз (1, 5, 10 лет) по методу «кирпичиков доходности»."""

    __tablename__ = "long_term_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    price_at_forecast: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    benchmark_key: Mapped[str] = mapped_column(String(32))
    benchmark_return_percent: Mapped[float] = mapped_column(Float)
    result_json: Mapped[str] = mapped_column(String(8000))
    confidence: Mapped[str] = mapped_column(String(16))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    def result(self) -> dict:
        import json

        return json.loads(self.result_json)


class ManualPrice(Base):
    """Цена, введённая вручную (для бумаг, которых нет в источниках)."""

    __tablename__ = "manual_prices"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JournalEntry(Base):
    """Запись журнала решений: что решил по акции и почему."""

    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(2), default="US")
    action: Mapped[str] = mapped_column(String(8))  # buy, sell, hold, watch
    reason: Mapped[str] = mapped_column(String(2000), default="")
    expectation: Mapped[str] = mapped_column(String(500), default="")  # что ожидаю и к какому сроку
    price_at_entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PriceAlert(Base):
    """Оповещение: цена поднялась выше или упала ниже заданного уровня."""

    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(2), default="US")
    direction: Mapped[str] = mapped_column(String(8))  # above, below
    target_price: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    triggered_price: Mapped[float | None] = mapped_column(Float, nullable=True)
