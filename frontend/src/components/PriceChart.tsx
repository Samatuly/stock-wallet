"use client";

import { useEffect, useState } from "react";
import Collapsible from "@/components/Collapsible";
import ForecastPanel from "@/components/ForecastPanel";
import LongTermPanel from "@/components/LongTermPanel";
import FundamentalsStrip from "@/components/FundamentalsStrip";
import { api, type IndicatorSeries } from "@/lib/api";
import { money } from "@/lib/format";

const WIDTH = 640;
const PAD = 8;
const PRICE_H = 130;
const RSI_H = 70;
const MACD_H = 80;

/** Строит путь SVG по значениям, пропуская null отдельными отрезками (обрыв линии,
 * а не соединение через дыру — важно, пока индикатор ещё не накопил данных). */
function buildPath(values: (number | null)[], xStep: number, yFor: (v: number) => number): string {
  let d = "";
  let drawing = false;
  values.forEach((v, i) => {
    if (v === null || Number.isNaN(v)) {
      drawing = false;
      return;
    }
    const x = PAD + i * xStep;
    const y = yFor(v);
    d += (drawing ? " L" : (d ? " M" : "M")) + `${x},${y}`;
    drawing = true;
  });
  return d;
}

function extent(groups: (number | null)[][]): [number, number] {
  const vals = groups.flat().filter((v): v is number => v !== null && !Number.isNaN(v));
  if (vals.length === 0) return [0, 1];
  return [Math.min(...vals), Math.max(...vals)];
}

export default function PriceChart({
  ticker,
  currency,
  buyPrice,
}: {
  ticker: string;
  currency: string;
  buyPrice: number;
}) {
  const [data, setData] = useState<IndicatorSeries | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .indicators(ticker, 220)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Не удалось загрузить историю");
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (error) return <p className="warning">{error}</p>;
  if (data === null) return <p className="empty">Загружаю историю цены…</p>;
  if (data.close.length < 2) {
    return <p className="empty">История цены для {ticker} пока недоступна.</p>;
  }

  const n = data.close.length;
  const xStep = (WIDTH - PAD * 2) / (n - 1);
  const first = data.close[0];
  const last = data.close[n - 1];
  const up = last >= first;

  // --- Цена + SMA ---
  const [pMin, pMax] = extent([data.close, data.sma_20, data.sma_50]);
  const pRange = pMax - pMin || 1;
  const yPrice = (v: number) => PRICE_H - PAD - ((v - pMin) / pRange) * (PRICE_H - PAD * 2);
  const priceClose = buildPath(data.close, xStep, yPrice);
  const priceSma20 = buildPath(data.sma_20, xStep, yPrice);
  const priceSma50 = buildPath(data.sma_50, xStep, yPrice);

  // --- RSI: фиксированный диапазон 0-100, линии-ориентиры на 30 и 70 ---
  const yRsi = (v: number) => RSI_H - PAD - (v / 100) * (RSI_H - PAD * 2);
  const rsiPath = buildPath(data.rsi_14, xStep, yRsi);
  const lastRsi = [...data.rsi_14].reverse().find((v) => v !== null) ?? null;

  // --- MACD: симметричный диапазон вокруг нуля, гистограмма столбиками ---
  const [mMinRaw, mMaxRaw] = extent([data.macd, data.macd_signal, data.macd_histogram]);
  const mBound = Math.max(Math.abs(mMinRaw), Math.abs(mMaxRaw)) || 1;
  const yMacd = (v: number) => MACD_H / 2 - (v / mBound) * (MACD_H / 2 - PAD);
  const macdPath = buildPath(data.macd, xStep, yMacd);
  const signalPath = buildPath(data.macd_signal, xStep, yMacd);
  const zeroY = yMacd(0);

  return (
    <div className="chart">
      <div className="chart-panel">
        <div className="chart-legend">
          <span className="legend-item"><span className="swatch" style={{ background: up ? "var(--gain)" : "var(--loss)" }} />Цена</span>
          <span className="legend-item"><span className="swatch" style={{ background: "var(--attn)" }} />SMA 20</span>
          <span className="legend-item"><span className="swatch" style={{ background: "var(--market-kz)" }} />SMA 50</span>
        </div>
        <svg viewBox={`0 0 ${WIDTH} ${PRICE_H}`} width="100%" height={PRICE_H} preserveAspectRatio="none">
          <path d={priceSma50} fill="none" stroke="var(--market-kz)" strokeWidth={1.5} opacity={0.8} />
          <path d={priceSma20} fill="none" stroke="var(--attn)" strokeWidth={1.5} opacity={0.8} />
          <path d={priceClose} fill="none" stroke={up ? "var(--gain)" : "var(--loss)"} strokeWidth={2} />
        </svg>
        <div className="chart-meta">
          <span>{data.dates[0]}</span>
          <span>{money(pMin, currency)} – {money(pMax, currency)}</span>
          <span>{data.dates[n - 1]}</span>
        </div>
      </div>

      <div className="chart-panel">
        <div className="chart-legend">
          <span className="legend-item"><span className="swatch" style={{ background: "var(--accent)" }} />RSI 14</span>
          {lastRsi !== null && <span className="chart-current">{lastRsi.toFixed(1)}</span>}
        </div>
        <svg viewBox={`0 0 ${WIDTH} ${RSI_H}`} width="100%" height={RSI_H} preserveAspectRatio="none">
          <line x1={PAD} x2={WIDTH - PAD} y1={yRsi(70)} y2={yRsi(70)} stroke="var(--rule)" strokeDasharray="3 3" />
          <line x1={PAD} x2={WIDTH - PAD} y1={yRsi(30)} y2={yRsi(30)} stroke="var(--rule)" strokeDasharray="3 3" />
          <path d={rsiPath} fill="none" stroke="var(--accent)" strokeWidth={1.75} />
        </svg>
        <div className="chart-meta"><span>30 / 70 — ориентиры перепроданности и перекупленности</span></div>
      </div>

      <div className="chart-panel">
        <div className="chart-legend">
          <span className="legend-item"><span className="swatch" style={{ background: "var(--accent)" }} />MACD</span>
          <span className="legend-item"><span className="swatch" style={{ background: "var(--attn)" }} />Сигнальная</span>
        </div>
        <svg viewBox={`0 0 ${WIDTH} ${MACD_H}`} width="100%" height={MACD_H} preserveAspectRatio="none">
          <line x1={PAD} x2={WIDTH - PAD} y1={zeroY} y2={zeroY} stroke="var(--rule)" />
          {data.macd_histogram.map((v, i) =>
            v === null ? null : (
              <rect
                key={i}
                x={PAD + i * xStep - 1}
                y={v >= 0 ? yMacd(v) : zeroY}
                width={Math.max(xStep - 1, 1)}
                height={Math.abs(yMacd(v) - zeroY)}
                fill={v >= 0 ? "var(--gain)" : "var(--loss)"}
                opacity={0.5}
              />
            )
          )}
          <path d={macdPath} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
          <path d={signalPath} fill="none" stroke="var(--attn)" strokeWidth={1.5} />
        </svg>
      </div>

      <FundamentalsStrip ticker={ticker} />
      <Collapsible title="Прогноз на 7–90 дней" hint="Monte Carlo + Claude">
        <ForecastPanel ticker={ticker} currency={currency} buyPrice={buyPrice} />
      </Collapsible>
      <Collapsible title="Прогноз на 1, 5 и 10 лет" hint="кирпичики доходности">
        <LongTermPanel ticker={ticker} currency={currency} />
      </Collapsible>
    </div>
  );
}
