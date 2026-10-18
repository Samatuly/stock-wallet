"use client";

import AppHeader from "@/components/AppHeader";
import { useCallback, useEffect, useState } from "react";
import AllocationBars, { MARKET_LABEL } from "@/components/AllocationBars";
import BenchmarkCard from "@/components/BenchmarkCard";
import RankedPositions from "@/components/RankedPositions";
import VolatilityTable from "@/components/VolatilityTable";
import { api, type Dashboard } from "@/lib/api";
import { money, number } from "@/lib/format";

const CURRENCIES = ["USD", "EUR", "KZT", "GBP"];

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currency, setCurrency] = useState("USD");

  const load = useCallback(async () => {
    try {
      setData(await api.dashboard(currency));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить дашборд");
    }
  }, [currency]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main>
      <AppHeader title="Дашборд" />

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}

      {!data && !error && <p className="empty">Загружаю дашборд…</p>}

      {data && (
        <>
          <section className="combined">
            <div className="currency-switch" role="group" aria-label="Валюта отображения">
              {CURRENCIES.map((c) => (
                <button key={c} className={c === currency ? "active" : ""} onClick={() => setCurrency(c)}>
                  {c}
                </button>
              ))}
            </div>
            <div className="combined-value">{money(data.total_value, data.display_currency)}</div>
            <div className="combined-meta">
              {data.rate_date ? `Курс на ${data.rate_date}` : "Курс недоступен"}
              {data.missing_currencies.length > 0 &&
                ` · не удалось конвертировать: ${data.missing_currencies.join(", ")}`}
            </div>
          </section>

          {data.portfolio_volatility_weighted !== null && (
            <div className="card vol-headline">
              <span>Волатильность портфеля (средняя по позициям, взвешенная по доле)</span>
              <strong>{number(data.portfolio_volatility_weighted, 1)}%</strong>
            </div>
          )}

          <div className="dashboard-grid">
            <div className="card">
              <AllocationBars
                title="По рынку"
                items={data.allocation_by_market}
                currency={data.display_currency}
                labelMap={MARKET_LABEL}
              />
            </div>
            <div className="card">
              <AllocationBars title="По валюте" items={data.allocation_by_currency} currency={data.display_currency} />
            </div>
            <div className="card">
              <AllocationBars title="По бумаге" items={data.allocation_by_ticker} currency={data.display_currency} />
            </div>
          </div>

          <div className="dashboard-grid">
            <div className="card">
              <RankedPositions title="Лидеры по доходности" positions={data.top_positions} />
            </div>
            <div className="card">
              <RankedPositions title="Аутсайдеры" positions={data.bottom_positions} />
            </div>
          </div>

          <div className="card">
            <VolatilityTable rows={data.volatility} />
          </div>

          <BenchmarkCard data={data.benchmark} />
        </>
      )}
    </main>
  );
}
