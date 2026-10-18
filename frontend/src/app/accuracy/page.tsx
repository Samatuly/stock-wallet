"use client";

import AppHeader from "@/components/AppHeader";
import { useEffect, useState } from "react";
import { api, type AccuracySummary } from "@/lib/api";
import { money, number, signedPercent, tone } from "@/lib/format";

export default function AccuracyPage() {
  const [data, setData] = useState<AccuracySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.accuracy().then(setData).catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить данные"));
  }, []);

  const beatsNaive =
    data && data.mean_abs_pct_error_vs_monte_carlo_p50 !== null && data.mean_abs_pct_error_naive !== null
      ? data.mean_abs_pct_error_vs_monte_carlo_p50 < data.mean_abs_pct_error_naive
      : null;

  return (
    <main>
      <AppHeader title="Точность прогнозов" />

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p className="empty">Сверяю прогнозы с фактическими ценами…</p>}

      {data && (
        <>
          <p className="hint">
            Краткосрочный прогноз «созревает» через выбранное число дней. Тогда берётся фактическая цена закрытия и
            сравнивается с прогнозом. Для сравнения есть простейший прогноз «цена не изменится»: если прогнозы Claude и
            статистики не точнее него, доверять им пока рано.
          </p>

          <div className="accuracy-stats">
            <div className="card">
              <h3>Проверено / ждут срока</h3>
              <div className="accuracy-big">
                {data.total_evaluated} / {data.total_pending}
              </div>
            </div>
            <div className="card">
              <h3>Цена попала в базовый диапазон</h3>
              <div className="accuracy-big">
                {data.hit_rate_base_range_percent !== null ? `${number(data.hit_rate_base_range_percent, 0)}%` : "—"}
              </div>
            </div>
            <div className="card">
              <h3>Средняя ошибка к медиане Monte Carlo</h3>
              <div className="accuracy-big">
                {data.mean_abs_pct_error_vs_monte_carlo_p50 !== null ? `${number(data.mean_abs_pct_error_vs_monte_carlo_p50, 1)}%` : "—"}
              </div>
            </div>
            <div className="card">
              <h3>Ошибка «цена не изменится»</h3>
              <div className="accuracy-big">
                {data.mean_abs_pct_error_naive !== null ? `${number(data.mean_abs_pct_error_naive, 1)}%` : "—"}
              </div>
            </div>
          </div>

          {beatsNaive !== null && (
            <p className="hint">
              {beatsNaive
                ? "Пока медиана Monte Carlo ошибается меньше, чем «цена не изменится»."
                : "Пока медиана Monte Carlo не точнее, чем «цена не изменится»."}{" "}
              Выборка мала, пока проверено {data.total_evaluated} прогнозов, выводы предварительные.
            </p>
          )}

          {data.items.length === 0 ? (
            <p className="empty">Прогнозов пока нет. Запросите прогноз на карточке акции, и он появится здесь.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Акция</th>
                    <th>Горизонт</th>
                    <th>Срок</th>
                    <th>Цена тогда</th>
                    <th>Базовый диапазон</th>
                    <th>Факт</th>
                    <th>Попал</th>
                    <th>К медиане MC</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((i, idx) => (
                    <tr key={idx}>
                      <td>{i.ticker}</td>
                      <td className="num">{i.horizon_days} дн.</td>
                      <td className="num">{i.due_date}</td>
                      <td className="num">{number(i.price_at_forecast, 2)}</td>
                      <td className="num">
                        {i.base_price_low !== null && i.base_price_high !== null
                          ? `${number(i.base_price_low, 2)} – ${number(i.base_price_high, 2)}`
                          : "—"}
                      </td>
                      <td className="num">{i.actual_price !== null ? number(i.actual_price, 2) : "ждём"}</td>
                      <td>{i.hit_base_range === null ? "—" : i.hit_base_range ? "да" : "нет"}</td>
                      <td className={`num ${tone(i.pct_error_vs_monte_carlo_p50)}`}>
                        {signedPercent(i.pct_error_vs_monte_carlo_p50)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  );
}
