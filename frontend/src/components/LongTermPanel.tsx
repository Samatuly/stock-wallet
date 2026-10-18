"use client";

import { useEffect, useState } from "react";
import { api, type LongTermForecast, type LongTermScenario } from "@/lib/api";
import { money, number, signedPercent, tone } from "@/lib/format";

const SCENARIO_LABEL: Record<LongTermScenario["name"], string> = {
  optimistic: "Оптимистичный",
  base: "Базовый",
  pessimistic: "Пессимистичный",
};

const CONFIDENCE_LABEL = { low: "низкая", medium: "средняя", high: "высокая" } as const;

export default function LongTermPanel({ ticker, currency }: { ticker: string; currency: string }) {
  const [data, setData] = useState<LongTermForecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    setChecked(false);
    api
      .getLongTerm(ticker)
      .then((f) => {
        if (!cancelled) {
          setData(f);
          setChecked(true);
        }
      })
      .catch(() => {
        if (!cancelled) setChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  async function request(refresh: boolean) {
    setLoading(true);
    setError(null);
    try {
      setData(await api.createLongTerm(ticker, refresh));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось получить долгосрочный прогноз");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="forecast-panel">
      <p className="hint">
        Метод «кирпичиков доходности»: рост выручки + выкуп акций + изменение маржи + изменение оценки (P/E) + дивиденды.
        Claude предлагает допущения, а цены считает программа. Банки публикуют такие оценки для рынков, а не для отдельных
        акций, поэтому неопределённость высокая. Это не инвестиционная рекомендация.
      </p>

      {!checked && <p className="empty">Проверяю сохранённый прогноз…</p>}
      {checked && !data && !loading && <button onClick={() => request(false)}>Запросить долгосрочный прогноз</button>}
      {loading && <p className="empty">Спрашиваю Claude, это может занять до минуты…</p>}
      {error && <p className="warning">{error}</p>}

      {data && (
        <div className="forecast-body">
          <p className="forecast-summary">{data.summary}</p>

          <div className="table-wrap">
            <table className="longterm-table">
              <thead>
                <tr>
                  <th>Сценарий</th>
                  <th>Вероятность</th>
                  <th>В год</th>
                  <th>1 год</th>
                  <th>5 лет</th>
                  <th>10 лет</th>
                </tr>
              </thead>
              <tbody>
                {data.scenarios.map((s) => (
                  <tr key={s.name}>
                    <td>{SCENARIO_LABEL[s.name]}</td>
                    <td className="num">{number(s.probability * 100, 0)}%</td>
                    <td className={`num ${tone(s.annual_total_return_percent)}`}>{signedPercent(s.annual_total_return_percent)}</td>
                    {s.points.map((p) => (
                      <td key={p.years} className="num">
                        {money(p.price, data.currency)}
                        <span className={`longterm-sub ${tone(p.total_return_percent)}`}>{signedPercent(p.total_return_percent)}</span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="forecast-stats">
            <div>
              Взвешенная доходность по сценариям (с дивидендами):{" "}
              <strong>{signedPercent(data.weighted_base_return_percent)}</strong> в год. Ориентир рынка ({data.benchmark_name},
              J.P. Morgan LTCMA 2026): <strong>{signedPercent(data.benchmark_return_percent)}</strong> в год.
            </div>
            {data.benchmark_comparison_note && <div>{data.benchmark_comparison_note}</div>}
            <div>
              Исходные данные: P/E {data.pe_ratio !== null ? number(data.pe_ratio, 1) : "—"}, дивиденды{" "}
              {data.dividend_yield_percent !== null ? `${number(data.dividend_yield_percent, 2)}%` : "—"}. Уверенность:{" "}
              {CONFIDENCE_LABEL[data.confidence]}
            </div>
          </div>

          <details className="longterm-details">
            <summary>Допущения по сценариям (в процентах за год)</summary>
            {data.scenarios.map((s) => (
              <div key={s.name} className="longterm-assumption">
                <strong>{SCENARIO_LABEL[s.name]}:</strong> выручка {signedPercent(s.revenue_growth_percent)}, выкуп акций{" "}
                {signedPercent(s.net_buyback_percent)}, маржа {signedPercent(s.margin_change_percent)}, оценка (P/E){" "}
                {signedPercent(s.valuation_change_percent)}. {s.rationale}
              </div>
            ))}
          </details>

          {data.data_gaps.length > 0 && <p className="hint-inline">Чего не хватило в данных: {data.data_gaps.join("; ")}</p>}

          <div className="forecast-meta">
            <span>
              {data.from_cache ? "Из сохранённого прогноза (живёт 30 дней)" : "Только что посчитан"} ·{" "}
              {new Date(data.created_at).toLocaleString("ru-RU")} · цена на тот момент: {money(data.price_at_forecast, currency)}
            </span>
            <button className="link" onClick={() => request(true)} disabled={loading}>
              Пересчитать (${data.cost_usd.toFixed(3)} за запрос)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
