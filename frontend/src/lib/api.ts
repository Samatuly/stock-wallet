const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Market = "US" | "EU" | "KZ";

export interface Valuation {
  id: number;
  ticker: string;
  market: Market;
  quantity: number;
  buy_price: number;
  buy_date: string;
  fee: number;
  currency: string;
  note: string;
  current_price: number | null;
  price_source: string | null;
  price_time: string | null;
  price_is_manual: boolean;
  cost: number;
  value: number | null;
  pnl_amount: number | null;
  pnl_percent: number | null;
  weight_percent: number | null;
  warning: string | null;
}

export interface CurrencyTotal {
  currency: string;
  cost: number;
  value: number;
  pnl_amount: number;
  pnl_percent: number | null;
  priced_count: number;
  unpriced_count: number;
}

export interface CombinedTotal {
  currency: string;
  value: number;
  cost: number;
  pnl_amount: number;
  pnl_percent: number | null;
  rate_date: string | null;
  is_stale: boolean;
  missing_currencies: string[];
}

export interface Portfolio {
  positions: Valuation[];
  totals: CurrencyTotal[];
  combined: CombinedTotal | null;
}

export interface NewPosition {
  ticker: string;
  market: Market;
  quantity: number;
  buy_price: number;
  buy_date: string;
  fee: number;
  currency: string;
  note: string;
}

export interface AllocationItem {
  label: string;
  value: number;
  percent: number;
}

export interface PositionRisk {
  ticker: string;
  volatility_annualized: number | null;
  data_points: number;
}

export interface Dashboard {
  benchmark: BenchmarkComparison | null;
  display_currency: string;
  total_value: number;
  allocation_by_market: AllocationItem[];
  allocation_by_currency: AllocationItem[];
  allocation_by_ticker: AllocationItem[];
  top_positions: Valuation[];
  bottom_positions: Valuation[];
  volatility: PositionRisk[];
  portfolio_volatility_weighted: number | null;
  rate_date: string | null;
  missing_currencies: string[];
}

export interface IndicatorSeries {
  dates: string[];
  close: number[];
  sma_20: (number | null)[];
  sma_50: (number | null)[];
  rsi_14: (number | null)[];
  macd: (number | null)[];
  macd_signal: (number | null)[];
  macd_histogram: (number | null)[];
}

export interface Fundamentals {
  ticker: string;
  pe_ratio: number | null;
  dividend_yield: number | null;
  next_earnings_date: string | null;
  currency: string | null;
  source: string;
  fetched_at: string;
  is_stale: boolean;
}

export interface BenchmarkComparison {
  benchmark_name: string;
  display_currency: string;
  portfolio_return_percent: number;
  benchmark_return_percent: number;
  since_date: string;
  skipped_tickers: string[];
  missing_currencies: string[];
}

export interface ForecastScenario {
  name: "optimistic" | "base" | "pessimistic";
  probability: number;
  price_low: number;
  price_high: number;
  drivers: string[];
}

export interface ForecastResult {
  summary: string;
  scenarios: ForecastScenario[];
  prob_above_buy_price: number | null;
  key_risks: string[];
  confidence: "low" | "medium" | "high";
  data_gaps: string[];
}

export interface MonteCarloOut {
  p10: number;
  p50: number;
  p90: number;
  prob_above_buy_price: number | null;
  paths: number;
  mu_annual: number;
  sigma_annual: number;
}

export interface Forecast {
  ticker: string;
  horizon_days: number;
  created_at: string;
  price_at_forecast: number;
  currency: string;
  monte_carlo: MonteCarloOut;
  result: ForecastResult;
  cost_usd: number;
  from_cache: boolean;
}

export interface BudgetStatus {
  month: string;
  spent_usd: number;
  limit_usd: number;
  remaining_usd: number;
  is_over_limit: boolean;
}

export interface LongTermPoint {
  years: number;
  price: number;
  total_return_percent: number;
}

export interface LongTermScenario {
  name: "optimistic" | "base" | "pessimistic";
  probability: number;
  rationale: string;
  revenue_growth_percent: number;
  net_buyback_percent: number;
  margin_change_percent: number;
  valuation_change_percent: number;
  annual_price_return_percent: number;
  annual_total_return_percent: number;
  points: LongTermPoint[];
}

export interface LongTermForecast {
  ticker: string;
  created_at: string;
  price_at_forecast: number;
  currency: string;
  dividend_yield_percent: number | null;
  pe_ratio: number | null;
  benchmark_name: string;
  benchmark_return_percent: number;
  weighted_base_return_percent: number;
  summary: string;
  scenarios: LongTermScenario[];
  benchmark_comparison_note: string;
  confidence: "low" | "medium" | "high";
  data_gaps: string[];
  cost_usd: number;
  from_cache: boolean;
}

export interface AccuracyItem {
  ticker: string;
  horizon_days: number;
  created_at: string;
  due_date: string;
  price_at_forecast: number;
  actual_price: number | null;
  base_price_low: number | null;
  base_price_high: number | null;
  monte_carlo_p50: number | null;
  hit_base_range: boolean | null;
  pct_error_vs_monte_carlo_p50: number | null;
  pct_error_naive: number | null;
}

export interface AccuracySummary {
  total_evaluated: number;
  total_pending: number;
  hit_rate_base_range_percent: number | null;
  mean_abs_pct_error_vs_monte_carlo_p50: number | null;
  mean_abs_pct_error_naive: number | null;
  items: AccuracyItem[];
}

export interface ImportRow {
  line: number;
  ticker: string;
  market: Market;
  quantity: number;
  buy_price: number;
  buy_date: string;
  fee: number;
  currency: string;
  note: string;
  duplicate: boolean;
}

export interface ImportResult {
  rows: ImportRow[];
  errors: { line: number; message: string }[];
  imported: number;
  skipped_duplicates: number;
}

export type JournalAction = "buy" | "sell" | "hold" | "watch";

export interface JournalEntry {
  id: number;
  ticker: string;
  market: Market;
  action: JournalAction;
  reason: string;
  expectation: string;
  price_at_entry: number | null;
  currency: string | null;
  created_at: string;
  current_price: number | null;
  change_percent: number | null;
}

export interface NewJournalEntry {
  ticker: string;
  market: Market;
  action: JournalAction;
  reason: string;
  expectation: string;
}

export interface PriceAlert {
  id: number;
  ticker: string;
  market: Market;
  direction: "above" | "below";
  target_price: number;
  note: string;
  active: boolean;
  created_at: string;
  triggered_at: string | null;
  triggered_price: number | null;
  current_price: number | null;
}

export interface NewPriceAlert {
  ticker: string;
  market: Market;
  direction: "above" | "below";
  target_price: number;
  note: string;
}

export interface WhatIfRequest {
  display_currency: string;
  market_shocks: Record<string, number>;
  ticker_shocks: Record<string, number>;
  fx_shocks: Record<string, number>;
}

export interface WhatIfPosition {
  ticker: string;
  market: Market;
  currency: string;
  value_now: number;
  value_after: number;
  delta: number;
  price_change_percent: number;
  fx_change_percent: number;
}

export interface WhatIfResult {
  display_currency: string;
  value_now: number;
  value_after: number;
  delta: number;
  delta_percent: number | null;
  cost: number;
  pnl_now: number;
  pnl_after: number;
  positions: WhatIfPosition[];
  skipped_tickers: string[];
  rate_date: string | null;
}

export interface HistoryPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new Error(`Нет связи с бэкендом (${BASE}). Проверьте, что он запущен.`);
  }
  if (!res.ok) {
    let detail = `Ошибка ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) {
        detail = body.detail.map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ");
      }
    } catch {
      /* тело ответа не JSON */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  portfolio: (refresh: boolean, displayCurrency: string) =>
    request<Portfolio>(
      `/portfolio?display_currency=${displayCurrency}${refresh ? "&refresh=true" : ""}`
    ),
  addPosition: (p: NewPosition) => request("/positions", { method: "POST", body: JSON.stringify(p) }),
  updatePosition: (id: number, p: NewPosition) =>
    request(`/positions/${id}`, { method: "PUT", body: JSON.stringify(p) }),
  history: (ticker: string, days = 180) =>
    request<HistoryPoint[]>(`/quotes/${ticker}/history?days=${days}`),
  dashboard: (displayCurrency: string) =>
    request<Dashboard>(`/dashboard?display_currency=${displayCurrency}`),
  indicators: (ticker: string, days = 220) =>
    request<IndicatorSeries>(`/quotes/${ticker}/indicators?days=${days}`),
  fundamentals: (ticker: string) => request<Fundamentals>(`/quotes/${ticker}/fundamentals`),
  getForecast: (ticker: string, horizonDays: number) =>
    request<Forecast | null>(`/forecasts/${ticker}?horizon_days=${horizonDays}`),
  createForecast: (ticker: string, horizonDays: number, buyPrice?: number, refresh = false) =>
    request<Forecast>(`/forecasts/${ticker}`, {
      method: "POST",
      body: JSON.stringify({ horizon_days: horizonDays, buy_price: buyPrice, refresh }),
    }),
  getLongTerm: (ticker: string) => request<LongTermForecast | null>(`/forecasts/${ticker}/long-term`),
  createLongTerm: (ticker: string, refresh = false) =>
    request<LongTermForecast>(`/forecasts/${ticker}/long-term`, {
      method: "POST",
      body: JSON.stringify({ refresh }),
    }),
  accuracy: () => request<AccuracySummary>("/forecasts/accuracy"),
  importCsv: (csvText: string, dryRun: boolean) =>
    request<ImportResult>("/positions/import", {
      method: "POST",
      body: JSON.stringify({ csv_text: csvText, dry_run: dryRun }),
    }),
  journal: (ticker?: string) => request<JournalEntry[]>(`/journal${ticker ? `?ticker=${ticker}` : ""}`),
  addJournal: (e: NewJournalEntry) => request<JournalEntry>("/journal", { method: "POST", body: JSON.stringify(e) }),
  deleteJournal: (id: number) => request<void>(`/journal/${id}`, { method: "DELETE" }),
  alerts: () => request<PriceAlert[]>("/alerts"),
  addAlert: (a: NewPriceAlert) => request<PriceAlert>("/alerts", { method: "POST", body: JSON.stringify(a) }),
  deleteAlert: (id: number) => request<void>(`/alerts/${id}`, { method: "DELETE" }),
  checkAlerts: () => request<PriceAlert[]>("/alerts/check", { method: "POST" }),
  whatIf: (req: WhatIfRequest) =>
    request<WhatIfResult>("/whatif", { method: "POST", body: JSON.stringify(req) }),
  forecastBudget: () => request<BudgetStatus>("/forecasts/_budget/status"),
  deletePosition: (id: number) => request<void>(`/positions/${id}`, { method: "DELETE" }),
  setManualPrice: (ticker: string, price: number, currency: string) =>
    request("/manual-prices", { method: "PUT", body: JSON.stringify({ ticker, price, currency }) }),
};
