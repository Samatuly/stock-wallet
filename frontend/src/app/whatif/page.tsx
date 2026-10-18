"use client";

import AppHeader from "@/components/AppHeader";
import { useEffect, useMemo, useState } from "react";
import { api, type Portfolio, type WhatIfResult } from "@/lib/api";
import { money, signedMoney, signedPercent, tone } from "@/lib/format";

const CURRENCIES = ["USD", "EUR", "KZT", "GBP"];
const MARKET_LABEL: Record<string, string> = { US: "США", EU: "Европа", KZ: "Казахстан" };

const PRESETS: { label: string; markets: Record<string, number>; fx: Record<string, number> }[] = [
  { label: "Все рынки −20%", markets: { US: -20, EU: -20, KZ: -20 }, fx: {} },
  { label: "Все рынки −10%", markets: { US: -10, EU: -10, KZ: -10 }, fx: {} },
  { label: "Все рынки +10%", markets: { US: 10, EU: 10, KZ: 10 }, fx: {} },
  { label: "Тенге −10% к валюте отображения", markets: {}, fx: { KZT: -10 } },
];

export default function WhatIfPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [currency, setCurrency] = useState("USD");
  const [markets, setMarkets] = useState<Record<string, number>>({});
  const [tickers, setTickers] = useState<Record<string, number>>({});
  const [fx, setFx] = useState<Record<string, number>>({});
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.portfolio(false, "USD").then(setPortfolio).catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить портфель"));
  }, []);

  const presentMarkets = useMemo(
    () => Array.from(new Set(portfolio?.positions.map((p) => p.market) ?? [])),
    [portfolio]
  );
  const presentTickers = useMemo(
    () => Array.from(new Set(portfolio?.positions.map((p) => p.ticker) ?? [])),
    [portfolio]
  );
  const foreignCurrencies = useMemo(
    () => Array.from(new Set(portfolio?.positions.map((p) => p.currency) ?? [])).filter((c) => c !== currency),
    [portfolio, currency]
  );

  // Пересчёт с небольшой задержкой, чтобы не слать запрос на каждое движение ползунка.
  useEffect(() => {
    if (!portfolio) return;
    const timer = setTimeout(() => {
      api
        .whatIf({ display_currency: currency, market_shocks: markets, ticker_shocks: tickers, fx_shocks: fx })
        .then((r) => {
          setResult(r);
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : "Не удалось посчитать сценарий"));
    }, 350);
    return () => clearTimeout(timer);
  }, [portfolio, currency, markets, tickers, fx]);

  function setNum(setter: (f: (prev: Record<string, number>) => Record<string, number>) => void, key: string, raw: string) {
    const value = Number(raw.replace(",", "."));
    setter((prev) => {
      const next = { ...prev };
      if (raw.trim() === "" || Number.isNaN(value) || value === 0) delete next[key];
      else next[key] = value;
      return next;
    });
  }

  function reset() {
    setMarkets({});
    setTickers({});
    setFx({});
  }

  return (
    <main>
      <AppHeader title="Что-если" />

      <section className="card">
        <p className="hint">
          Посмотрите, сколько стоил бы портфель при заданных изменениях цен и курсов. Это арифметика на текущих данных, а не
          прогноз: связи между акциями не учитываются, каждое изменение применяется ровно так, как вы его задали. Ничего не
          сохраняется.
        </p>

        <div className="currency-switch" role="group" aria-label="Валюта отображения">
          {CURRENCIES.map((c) => (
            <button key={c} className={c === currency ? "active" : ""} onClick={() => setCurrency(c)}>
              {c}
            </button>
          ))}
        </div>

        <div className="whatif-presets">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              className="link"
              onClick={() => {
                setMarkets(p.markets);
                setFx(p.fx);
                setTickers({});
              }}
            >
              {p.label}
            </button>
          ))}
          <button className="link" onClick={reset}>
            Сбросить
          </button>
        </div>
      </section>

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}
      {!portfolio && !error && <p className="empty">Загружаю портфель…</p>}
      {portfolio && portfolio.positions.length === 0 && <p className="empty">В портфеле пока нет позиций.</p>}

      {portfolio && portfolio.positions.length > 0 && (
        <>
          <section className="card">
            <h2>Изменение цен, %</h2>
            <div className="whatif-grid">
              {presentMarkets.map((m) => (
                <label key={m}>
                  Все акции: {MARKET_LABEL[m] ?? m}
                  <input
                    inputMode="decimal"
                    placeholder="0"
                    value={markets[m] ?? ""}
                    onChange={(e) => setNum(setMarkets, m, e.target.value)}
                  />
                </label>
              ))}
            </div>
            <details className="longterm-details">
              <summary>Отдельно по акциям (важнее, чем по рынку)</summary>
              <div className="whatif-grid">
                {presentTickers.map((t) => (
                  <label key={t}>
                    {t}
                    <input
                      inputMode="decimal"
                      placeholder="0"
                      value={tickers[t] ?? ""}
                      onChange={(e) => setNum(setTickers, t, e.target.value)}
                    />
                  </label>
                ))}
              </div>
            </details>

            {foreignCurrencies.length > 0 && (
              <>
                <h2>Изменение курса к {currency}, %</h2>
                <p className="hint">Минус означает, что валюта подешевела: например, −10 для KZT удешевляет тенговые позиции на 10%.</p>
                <div className="whatif-grid">
                  {foreignCurrencies.map((c) => (
                    <label key={c}>
                      {c}
                      <input
                        inputMode="decimal"
                        placeholder="0"
                        value={fx[c] ?? ""}
                        onChange={(e) => setNum(setFx, c, e.target.value)}
                      />
                    </label>
                  ))}
                </div>
              </>
            )}
          </section>

          {result && (
            <section className="card">
              <h2>Результат</h2>
              <div className="whatif-summary">
                <div>
                  <span className="benchmark-label">Сейчас</span>
                  <span className="whatif-big">{money(result.value_now, result.display_currency)}</span>
                </div>
                <div>
                  <span className="benchmark-label">После</span>
                  <span className="whatif-big">{money(result.value_after, result.display_currency)}</span>
                </div>
                <div>
                  <span className="benchmark-label">Разница</span>
                  <span className={`whatif-big ${tone(result.delta)}`}>
                    {signedMoney(result.delta, result.display_currency)} · {signedPercent(result.delta_percent)}
                  </span>
                </div>
              </div>
              <p className="hint">
                Результат к вложенному: сейчас {signedMoney(result.pnl_now, result.display_currency)}, после{" "}
                {signedMoney(result.pnl_after, result.display_currency)} (вложено {money(result.cost, result.display_currency)}{" "}
                по текущему курсу{result.rate_date ? `, курс на ${result.rate_date}` : ""}).
              </p>
              {result.skipped_tickers.length > 0 && (
                <p className="warning">
                  Не вошли в расчёт (нет цены или курса): {result.skipped_tickers.join(", ")}.
                </p>
              )}

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Акция</th>
                      <th>Цена, %</th>
                      <th>Курс, %</th>
                      <th>Сейчас</th>
                      <th>После</th>
                      <th>Разница</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.positions.map((p, i) => (
                      <tr key={`${p.ticker}-${i}`}>
                        <td>{p.ticker}</td>
                        <td className={`num ${tone(p.price_change_percent)}`}>{signedPercent(p.price_change_percent)}</td>
                        <td className={`num ${tone(p.fx_change_percent)}`}>{signedPercent(p.fx_change_percent)}</td>
                        <td className="num">{money(p.value_now, result.display_currency)}</td>
                        <td className="num">{money(p.value_after, result.display_currency)}</td>
                        <td className={`num ${tone(p.delta)}`}>{signedMoney(p.delta, result.display_currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
