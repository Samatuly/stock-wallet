"use client";

import { useEffect, useState } from "react";
import { api, type Forecast, type ForecastScenario } from "@/lib/api";
import { money, number, signedPercent } from "@/lib/format";

const HORIZONS = [
  { days: 7, label: "7 дней" },
  { days: 30, label: "30 дней" },
  { days: 90, label: "90 дней" },
];

const SCENARIO_LABEL: Record<ForecastScenario["name"], string> = {
  optimistic: "Оптимистичный",
  base: "Базовый",
  pessimistic: "Пессимистичный",
};

const CONFIDENCE_LABEL: Record<Forecast["result"]["confidence"], string> = {
  low: "низкая",
  medium: "средняя",
  high: "высокая",
};

export default function ForecastPanel({ ticker, currency, buyPrice }: { ticker: string; currency: string; buyPrice: number }) {
  const [horizon, setHorizon] = useState(30);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkedCache, setCheckedCache] = useState(false);

  // При смене горизонта сначала тихо проверяем, нет ли уже сохранённого прогноза —
  // чтобы не заставлять каждый раз нажимать кнопку, если он уже есть и свежий.
  useEffect(() => {
    let cancelled = false;
    setForecast(null);
    setError(null);
    setCheckedCache(false);
    api
      .getForecast(ticker, horizon)
      .then((f) => {
        if (!cancelled) {
          setForecast(f);
          setCheckedCache(true);
        }
      })
      .catch(() => {
        if (!cancelled) setCheckedCache(true);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, horizon]);

  async function requestForecast(refresh: boolean) {
    setLoading(true);
    setError(null);
    try {
      const result = await api.createForecast(ticker, horizon, buyPrice, refresh);
      setForecast(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось получить прогноз");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="forecast-panel">
      <div className="forecast-header">
        <span className="hint-inline">Горизонт прогноза</span>
        <div className="currency-switch" role="group" aria-label="Горизонт прогноза">
          {HORIZONS.map((h) => (
            <button key={h.days} className={h.days === horizon ? "active" : ""} onClick={() => setHorizon(h.days)}>
              {h.label}
            </button>
          ))}
        </div>
      </div>

      <p className="hint">
        Сценарии цены на основе статистики (Monte Carlo) и анализа Claude. Это не инвестиционная
        рекомендация, а диапазон при заданных допущениях — прошлая доходность не гарантирует будущую.
      </p>

      {!checkedCache && <p className="empty">Проверяю, есть ли сохранённый прогноз…</p>}

      {checkedCache && !forecast && !loading && (
        <button onClick={() => requestForecast(false)}>Запросить прогноз</button>
      )}

      {loading && <p className="empty">Считаю Monte Carlo и спрашиваю Claude…</p>}

      {error && <p className="warning">{error}</p>}

      {forecast && (
        <div className="forecast-body">
          <p className="forecast-summary">{forecast.result.summary}</p>

          <div className="forecast-scenarios">
            {forecast.result.scenarios.map((s) => (
              <div key={s.name} className={`forecast-scenario scenario-${s.name}`}>
                <div className="forecast-scenario-head">
                  <span>{SCENARIO_LABEL[s.name]}</span>
                  <span className="forecast-prob">{number(s.probability * 100, 0)}%</span>
                </div>
                <div className="forecast-range">
                  {money(s.price_low, currency)} – {money(s.price_high, currency)}
                </div>
                {s.drivers.length > 0 && (
                  <ul className="forecast-drivers">
                    {s.drivers.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>

          <div className="forecast-stats">
            {forecast.result.prob_above_buy_price !== null && (
              <div>
                Вероятность быть выше цены покупки ({money(buyPrice, currency)}):{" "}
                <strong>{number(forecast.result.prob_above_buy_price * 100, 0)}%</strong>
              </div>
            )}
            <div>
              Статистический диапазон (Monte Carlo, без поправки Claude): {money(forecast.monte_carlo.p10, currency)} –{" "}
              {money(forecast.monte_carlo.p90, currency)}, медиана {money(forecast.monte_carlo.p50, currency)}
            </div>
            <div>Уверенность: {CONFIDENCE_LABEL[forecast.result.confidence]}</div>
          </div>

          {forecast.result.key_risks.length > 0 && (
            <div className="forecast-risks">
              <strong>Риски:</strong> {forecast.result.key_risks.join("; ")}
            </div>
          )}

          {forecast.result.data_gaps.length > 0 && (
            <p className="hint-inline">Чего не хватило в данных: {forecast.result.data_gaps.join("; ")}</p>
          )}

          <div className="forecast-meta">
            <span>
              {forecast.from_cache ? "Из сохранённого прогноза" : "Только что посчитан"} ·{" "}
              {new Date(forecast.created_at).toLocaleString("ru-RU")} · цена на тот момент:{" "}
              {money(forecast.price_at_forecast, currency)}
            </span>
            <button className="link" onClick={() => requestForecast(true)} disabled={loading}>
              Пересчитать (${forecast.cost_usd.toFixed(3)} за запрос)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
