from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Market = Literal["US", "EU", "KZ"]


class PositionCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    market: Market = "US"
    quantity: float = Field(gt=0)
    buy_price: float = Field(gt=0)
    buy_date: date
    fee: float = Field(default=0.0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    note: str = Field(default="", max_length=500)

    @field_validator("ticker", "currency", mode="before")
    @classmethod
    def _clean_upper(cls, v):
        # Очистка идёт до проверки длины, иначе тикер из пробелов пройдёт проверку
        return v.strip().upper() if isinstance(v, str) else v


class PositionOut(PositionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PositionValuation(PositionOut):
    """Позиция вместе с текущей ценой и результатом."""

    current_price: Optional[float] = None
    price_source: Optional[str] = None
    price_time: Optional[datetime] = None
    price_is_manual: bool = False
    cost: float  # сколько потрачено: количество * цена покупки + комиссия
    value: Optional[float] = None  # текущая стоимость
    pnl_amount: Optional[float] = None
    pnl_percent: Optional[float] = None
    weight_percent: Optional[float] = None  # доля в портфеле в своей валюте
    warning: Optional[str] = None


class CurrencyTotal(BaseModel):
    currency: str
    cost: float
    value: float
    pnl_amount: float
    pnl_percent: Optional[float] = None
    priced_count: int
    unpriced_count: int


class CombinedTotal(BaseModel):
    """Стоимость всего портфеля, пересчитанная в одну выбранную валюту."""

    currency: str
    value: float
    cost: float
    pnl_amount: float
    pnl_percent: Optional[float] = None
    rate_date: Optional[date] = None
    is_stale: bool = False  # курсы взяты из устаревшего кэша (источник был недоступен)
    missing_currencies: list[str] = Field(default_factory=list)  # не удалось найти курс


class PortfolioOut(BaseModel):
    positions: list[PositionValuation]
    totals: list[CurrencyTotal]
    combined: Optional[CombinedTotal] = None


class ManualPriceIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    price: float = Field(gt=0)
    currency: Optional[str] = Field(default=None, max_length=8)

    @field_validator("ticker", mode="before")
    @classmethod
    def _clean_ticker(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("currency", mode="before")
    @classmethod
    def _clean_currency(cls, v):
        return v.strip().upper() if isinstance(v, str) and v.strip() else None


class HistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class AllocationItem(BaseModel):
    """Одна строка аллокации: сколько портфеля приходится на рынок/валюту/тикер."""

    label: str
    value: float
    percent: float


class PositionRisk(BaseModel):
    """Годовая волатильность одной позиции, посчитанная по истории цены."""

    ticker: str
    volatility_annualized: Optional[float] = None  # в процентах, например 32.4
    data_points: int  # сколько дневных точек истории использовано


class BenchmarkComparison(BaseModel):
    benchmark_name: str
    display_currency: str
    portfolio_return_percent: float
    benchmark_return_percent: float
    since_date: date
    skipped_tickers: list[str] = Field(default_factory=list)
    missing_currencies: list[str] = Field(default_factory=list)


class DashboardOut(BaseModel):
    display_currency: str
    total_value: float
    allocation_by_market: list[AllocationItem]
    allocation_by_currency: list[AllocationItem]
    allocation_by_ticker: list[AllocationItem]
    top_positions: list[PositionValuation]
    bottom_positions: list[PositionValuation]
    volatility: list[PositionRisk]
    portfolio_volatility_weighted: Optional[float] = None
    rate_date: Optional[date] = None
    missing_currencies: list[str] = Field(default_factory=list)
    benchmark: Optional[BenchmarkComparison] = None


class IndicatorSeries(BaseModel):
    dates: list[date]
    close: list[float]
    sma_20: list[Optional[float]]
    sma_50: list[Optional[float]]
    rsi_14: list[Optional[float]]
    macd: list[Optional[float]]
    macd_signal: list[Optional[float]]
    macd_histogram: list[Optional[float]]


class IntradayPointOut(BaseModel):
    time: datetime
    price: float


class IntradayOut(BaseModel):
    """Цены за последний торговый день с шагом 5 минут."""

    ticker: str
    points: list[IntradayPointOut]


class FundamentalsOut(BaseModel):
    ticker: str
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None  # в процентах
    next_earnings_date: Optional[date] = None
    currency: Optional[str] = None
    source: str
    fetched_at: datetime
    is_stale: bool = False


class ForecastScenario(BaseModel):
    name: Literal["optimistic", "base", "pessimistic"]
    probability: float = Field(ge=0, le=1)
    price_low: float
    price_high: float
    drivers: list[str] = Field(default_factory=list)


class ForecastResult(BaseModel):
    """То, что должен вернуть Claude — используется и для проверки ответа."""

    summary: str
    scenarios: list[ForecastScenario]
    prob_above_buy_price: Optional[float] = Field(default=None, ge=0, le=1)
    key_risks: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    data_gaps: list[str] = Field(default_factory=list)


class MonteCarloOut(BaseModel):
    p10: float
    p50: float
    p90: float
    prob_above_buy_price: Optional[float] = None
    paths: int
    mu_annual: float
    sigma_annual: float


class ForecastOut(BaseModel):
    ticker: str
    horizon_days: int
    created_at: datetime
    price_at_forecast: float
    currency: str
    monte_carlo: MonteCarloOut
    result: ForecastResult
    cost_usd: float
    from_cache: bool = False


class ForecastRequest(BaseModel):
    horizon_days: int = Field(default=30, description="Горизонт в днях: обычно 7, 30 или 90")
    buy_price: Optional[float] = Field(default=None, description="Цена покупки для расчёта вероятности быть в плюсе")
    refresh: bool = Field(default=False, description="Игнорировать кэш и запросить новый прогноз")


class BudgetStatus(BaseModel):
    month: str
    spent_usd: float
    limit_usd: float
    remaining_usd: float
    is_over_limit: bool


class LongTermScenarioInput(BaseModel):
    """Допущения Claude на один сценарий. Все числа — доли в год (0.05 = 5% в год)."""

    name: Literal["optimistic", "base", "pessimistic"]
    probability: float = Field(ge=0, le=1)
    revenue_growth_annual: float = Field(ge=-0.5, le=1.0)
    net_buyback_annual: float = Field(ge=-0.2, le=0.2)  # >0 выкуп акций, <0 допэмиссия
    margin_change_annual: float = Field(ge=-0.2, le=0.2)
    valuation_change_annual: float = Field(ge=-0.3, le=0.3)  # изменение P/E в год
    rationale: str


class LongTermForecastInput(BaseModel):
    """То, что должен вернуть Claude. Цены он НЕ считает — это делает код."""

    summary: str
    scenarios: list[LongTermScenarioInput]
    benchmark_comparison_note: str = ""
    confidence: Literal["low", "medium", "high"]
    data_gaps: list[str] = Field(default_factory=list)


class LongTermScenarioPoint(BaseModel):
    years: int
    price: float
    total_return_percent: float  # накопленная за весь срок, с дивидендами


class LongTermScenarioOut(BaseModel):
    name: Literal["optimistic", "base", "pessimistic"]
    probability: float
    rationale: str
    revenue_growth_percent: float
    net_buyback_percent: float
    margin_change_percent: float
    valuation_change_percent: float
    annual_price_return_percent: float
    annual_total_return_percent: float
    points: list[LongTermScenarioPoint]


class LongTermForecastOut(BaseModel):
    ticker: str
    created_at: datetime
    price_at_forecast: float
    currency: str
    dividend_yield_percent: Optional[float] = None
    pe_ratio: Optional[float] = None
    benchmark_name: str
    benchmark_return_percent: float
    weighted_base_return_percent: float  # вероятностно-взвешенная годовая полная доходность
    summary: str
    scenarios: list[LongTermScenarioOut]
    benchmark_comparison_note: str
    confidence: Literal["low", "medium", "high"]
    data_gaps: list[str]
    cost_usd: float
    from_cache: bool = False


class LongTermForecastRequest(BaseModel):
    refresh: bool = False


class ForecastAccuracyItem(BaseModel):
    ticker: str
    horizon_days: int
    created_at: datetime
    due_date: date
    price_at_forecast: float
    actual_price: Optional[float] = None  # None — срок ещё не наступил или нет цены
    base_price_low: Optional[float] = None
    base_price_high: Optional[float] = None
    monte_carlo_p50: Optional[float] = None
    hit_base_range: Optional[bool] = None
    pct_error_vs_monte_carlo_p50: Optional[float] = None  # (факт - p50) / p50 * 100
    pct_error_naive: Optional[float] = None  # (факт - цена тогда) / цена тогда * 100


class ForecastAccuracySummary(BaseModel):
    total_evaluated: int
    total_pending: int
    hit_rate_base_range_percent: Optional[float] = None
    mean_abs_pct_error_vs_monte_carlo_p50: Optional[float] = None
    mean_abs_pct_error_naive: Optional[float] = None
    items: list[ForecastAccuracyItem]


class QuoteOut(BaseModel):
    ticker: str
    price: float
    currency: Optional[str]
    source: str
    fetched_at: datetime
    is_manual: bool


# ---------- Импорт CSV ----------

class ImportRequest(BaseModel):
    csv_text: str = Field(min_length=1, max_length=2_000_000)
    dry_run: bool = True  # True: только показать, что будет импортировано


class ImportRow(PositionCreate):
    line: int
    duplicate: bool = False  # такая позиция уже есть, будет пропущена


class ImportError_(BaseModel):
    line: int
    message: str


class ImportResult(BaseModel):
    rows: list[ImportRow]
    errors: list[ImportError_]
    imported: int  # 0 при dry_run
    skipped_duplicates: int


# ---------- Журнал решений ----------

Action = Literal["buy", "sell", "hold", "watch"]


class JournalCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    market: Market = "US"
    action: Action
    reason: str = Field(default="", max_length=2000)
    expectation: str = Field(default="", max_length=500)

    @field_validator("ticker", mode="before")
    @classmethod
    def _upper(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class JournalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    market: Market
    action: Action
    reason: str
    expectation: str
    price_at_entry: Optional[float] = None
    currency: Optional[str] = None
    created_at: datetime
    current_price: Optional[float] = None
    change_percent: Optional[float] = None  # изменение цены с момента записи


# ---------- Алерты ----------

class AlertCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    market: Market = "US"
    direction: Literal["above", "below"]
    target_price: float = Field(gt=0)
    note: str = Field(default="", max_length=200)

    @field_validator("ticker", mode="before")
    @classmethod
    def _upper(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    market: Market
    direction: Literal["above", "below"]
    target_price: float
    note: str
    active: bool
    created_at: datetime
    triggered_at: Optional[datetime] = None
    triggered_price: Optional[float] = None
    current_price: Optional[float] = None


# ---------- Что-если ----------

class WhatIfRequest(BaseModel):
    display_currency: str = Field(default="USD", min_length=3, max_length=3)
    # Изменение цен акций в процентах: сразу по рынку и точечно по тикеру (тикер важнее рынка).
    market_shocks: dict[str, float] = Field(default_factory=dict)  # {"US": -20}
    ticker_shocks: dict[str, float] = Field(default_factory=dict)  # {"AAPL": -30}
    # Изменение курса валюты к валюте отображения: -10 значит, что валюта подешевела на 10%.
    fx_shocks: dict[str, float] = Field(default_factory=dict)  # {"KZT": -10}

    @field_validator("display_currency", mode="before")
    @classmethod
    def _upper_ccy(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("market_shocks", "ticker_shocks", mode="after")
    @classmethod
    def _check_price_shocks(cls, v):
        for key, pct in v.items():
            if not -100 <= pct <= 1000:
                raise ValueError(f"изменение цены для {key} должно быть от -100% до +1000%")
        return {k.strip().upper(): pct for k, pct in v.items()}

    @field_validator("fx_shocks", mode="after")
    @classmethod
    def _check_fx_shocks(cls, v):
        for key, pct in v.items():
            if not -90 <= pct <= 500:
                raise ValueError(f"изменение курса {key} должно быть от -90% до +500%")
        return {k.strip().upper(): pct for k, pct in v.items()}

    @field_validator("market_shocks", mode="after")
    @classmethod
    def _check_markets(cls, v):
        bad = [k for k in v if k not in ("US", "EU", "KZ")]
        if bad:
            raise ValueError(f"неизвестный рынок: {', '.join(bad)} (допустимы US, EU, KZ)")
        return v


class WhatIfPosition(BaseModel):
    ticker: str
    market: Market
    currency: str
    value_now: float  # в валюте отображения
    value_after: float
    delta: float
    price_change_percent: float
    fx_change_percent: float


class WhatIfResult(BaseModel):
    display_currency: str
    value_now: float
    value_after: float
    delta: float
    delta_percent: Optional[float] = None
    cost: float
    pnl_now: float
    pnl_after: float
    positions: list[WhatIfPosition]
    skipped_tickers: list[str] = Field(default_factory=list)  # нет цены или курса, в расчёт не вошли
    rate_date: Optional[date] = None
