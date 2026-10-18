"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Collapsible from "@/components/Collapsible";
import ForecastPanel from "@/components/ForecastPanel";
import LongTermPanel from "@/components/LongTermPanel";
import FundamentalsStrip from "@/components/FundamentalsStrip";
import { api, type IndicatorSeries, type Intraday } from "@/lib/api";
import { money, signedMoney, signedPercent, tone } from "@/lib/format";
import { niceTicks, periodStart, PERIODS, type PeriodKey } from "@/lib/chart";

const HEIGHT = 220;
const M = { top: 12, right: 64, bottom: 24, left: 4 };
const IND_H = 70;

interface Series {
  times: string[]; // ISO дата или дата-время
  close: number[];
  sma20: (number | null)[];
  sma50: (number | null)[];
  rsi: (number | null)[];
  macd: (number | null)[];
  signal: (number | null)[];
  hist: (number | null)[];
  intraday: boolean;
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
  const [period, setPeriod] = useState<PeriodKey>("6M");
  const [daily, setDaily] = useState<IndicatorSeries | null>(null);
  const [intraday, setIntraday] = useState<Intraday | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDaily(null);
    setError(null);
    // ~420 календарных дней: год на графике плюс запас, чтобы SMA 50 была видна с начала периода
    api
      .indicators(ticker, 420)
      .then((d) => !cancelled && setDaily(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Не удалось загрузить историю"));
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  useEffect(() => {
    if (period !== "1D" || intraday?.ticker === ticker.toUpperCase()) return;
    let cancelled = false;
    api
      .intraday(ticker)
      .then((d) => !cancelled && setIntraday(d))
      .catch(() => !cancelled && setIntraday({ ticker: ticker.toUpperCase(), points: [] }));
    return () => {
      cancelled = true;
    };
  }, [period, ticker, intraday]);

  const series: Series | null = useMemo(() => {
    if (period === "1D") {
      if (!intraday || intraday.ticker !== ticker.toUpperCase()) return null;
      const n = intraday.points.length;
      const nulls = Array<null>(n).fill(null);
      return {
        times: intraday.points.map((p) => p.time),
        close: intraday.points.map((p) => p.price),
        sma20: nulls, sma50: nulls, rsi: nulls, macd: nulls, signal: nulls, hist: nulls,
        intraday: true,
      };
    }
    if (!daily || daily.dates.length === 0) return null;
    const start = periodStart(daily.dates[daily.dates.length - 1], period);
    let i0 = daily.dates.findIndex((d) => d >= start);
    if (i0 < 0) i0 = 0;
    const s = <T,>(a: T[]) => a.slice(i0);
    return {
      times: s(daily.dates),
      close: s(daily.close),
      sma20: s(daily.sma_20),
      sma50: s(daily.sma_50),
      rsi: s(daily.rsi_14),
      macd: s(daily.macd),
      signal: s(daily.macd_signal),
      hist: s(daily.macd_histogram),
      intraday: false,
    };
  }, [period, daily, intraday, ticker]);

  return (
    <div className="chart">
      <div className="period-switch" role="tablist" aria-label="Период графика">
        {PERIODS.map((p) => (
          <button
            key={p.key}
            type="button"
            role="tab"
            aria-selected={period === p.key}
            className={period === p.key ? "active" : ""}
            onClick={() => setPeriod(p.key)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {error && period !== "1D" ? (
        <p className="warning">{error}</p>
      ) : series === null ? (
        <p className="empty chart-placeholder">Загружаю график…</p>
      ) : series.close.length < 2 ? (
        <p className="empty chart-placeholder">
          {period === "1D" ? "Внутридневных данных пока нет (биржа закрыта или источник недоступен)." : `История цены для ${ticker} недоступна.`}
        </p>
      ) : (
        <>
          <MainChart s={series} currency={currency} buyPrice={buyPrice} />
          {!series.intraday && (
            <Collapsible title="Технические индикаторы" hint="RSI 14, MACD">
              <Indicators s={series} />
            </Collapsible>
          )}
        </>
      )}

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

/* ---------------- Основной график цены ---------------- */

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    ro.observe(el);
    setWidth(Math.floor(el.getBoundingClientRect().width));
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function MainChart({ s, currency, buyPrice }: { s: Series; currency: string; buyPrice: number }) {
  const [wrapRef, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const [showSma, setShowSma] = useState(true);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => setActive(null), [s]);

  const n = s.close.length;
  const first = s.close[0];
  const last = s.close[n - 1];
  const shown = active ?? n - 1;
  const shownPrice = s.close[shown];
  const change = shownPrice - first;
  const changePct = first ? (change / first) * 100 : 0;
  const lineColor = last >= first ? "var(--gain)" : "var(--loss)";

  // На коротких периодах SMA почти прямые и только растягивают шкалу — показываем их от ~2 месяцев
  const smaAvailable = !s.intraday && n > 40;
  const smaOn = showSma && smaAvailable;
  const valuesForRange = [
    ...s.close,
    ...(smaOn ? [...s.sma20, ...s.sma50].filter((v): v is number => v !== null) : []),
  ];
  let lo = Math.min(...valuesForRange);
  let hi = Math.max(...valuesForRange);
  if (hi === lo) {
    hi += 1;
    lo -= 1;
  }
  const ticks = niceTicks(lo, hi, 5);
  const yMin = Math.min(lo, ticks[0]);
  const yMax = Math.max(hi, ticks[ticks.length - 1]);

  const innerW = Math.max(width - M.left - M.right, 10);
  const innerH = HEIGHT - M.top - M.bottom;
  const x = (i: number) => M.left + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => M.top + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  const pathOf = (vals: (number | null)[]) => {
    let d = "";
    let on = false;
    vals.forEach((v, i) => {
      if (v === null || Number.isNaN(v)) {
        on = false;
        return;
      }
      d += `${on ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      on = true;
    });
    return d;
  };
  const line = pathOf(s.close);
  const area = `${line}L${x(n - 1).toFixed(1)},${M.top + innerH}L${x(0).toFixed(1)},${M.top + innerH}Z`;

  const xTickIdx = xTickIndexes(n, width < 420 ? 3 : 5);
  const buyInRange = buyPrice >= yMin && buyPrice <= yMax;

  function pick(clientX: number) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = clientX - rect.left - M.left;
    const i = Math.round((px / innerW) * (n - 1));
    setActive(Math.max(0, Math.min(n - 1, i)));
  }

  return (
    <div className="price-chart">
      <div className="price-head">
        <div>
          <div className="price-big">{money(shownPrice, currency)}</div>
          <div className={`price-change ${tone(change)}`}>
            {signedMoney(change, currency)} ({signedPercent(changePct)})
            <span className="price-when">{active === null ? " с начала периода" : ` · ${formatFull(s.times[shown], s.intraday)}`}</span>
          </div>
        </div>
        {smaAvailable && (
          <label className="sma-toggle">
            <input type="checkbox" checked={showSma} onChange={(e) => setShowSma(e.target.checked)} />
            SMA 20/50
          </label>
        )}
      </div>

      <div ref={wrapRef} className="price-plot">
        {width > 0 && (
          <svg
            ref={svgRef}
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={`График цены: от ${money(first, currency)} до ${money(last, currency)}`}
            style={{ touchAction: "pan-y" }}
            onPointerDown={(e) => pick(e.clientX)}
            onPointerMove={(e) => {
              if (e.pointerType === "mouse" || e.buttons > 0) pick(e.clientX);
            }}
            onPointerLeave={(e) => {
              if (e.pointerType === "mouse") setActive(null);
            }}
          >
            <defs>
              <linearGradient id="pc-fill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={lineColor} stopOpacity={0.18} />
                <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
              </linearGradient>
            </defs>

            {/* Ось Y: сетка и подписи цен справа */}
            {ticks.map((t) => (
              <g key={t}>
                <line x1={M.left} x2={M.left + innerW} y1={y(t)} y2={y(t)} className="grid" />
                <text x={M.left + innerW + 8} y={y(t)} dy="0.32em" className="axis-label">
                  {compactPrice(t)}
                </text>
              </g>
            ))}

            {/* Ось X: даты или время */}
            {xTickIdx.map((i) => (
              <text
                key={i}
                x={x(i)}
                y={HEIGHT - 6}
                className="axis-label"
                textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}
              >
                {formatTick(s.times[i], s.intraday, s.times[0], s.times[n - 1])}
              </text>
            ))}

            {buyInRange && (
              <g>
                <line x1={M.left} x2={M.left + innerW} y1={y(buyPrice)} y2={y(buyPrice)} className="buy-line" />
                <text x={M.left + 4} y={y(buyPrice) - 5} className="buy-label">
                  ср. цена покупки
                </text>
              </g>
            )}

            <path d={area} fill="url(#pc-fill)" />
            {smaOn && <path d={pathOf(s.sma50)} fill="none" stroke="var(--market-kz)" strokeWidth={1.25} opacity={0.75} />}
            {smaOn && <path d={pathOf(s.sma20)} fill="none" stroke="var(--attn)" strokeWidth={1.25} opacity={0.75} />}
            <path d={line} fill="none" stroke={lineColor} strokeWidth={2} strokeLinejoin="round" />

            {active !== null && (
              <g pointerEvents="none">
                <line x1={x(active)} x2={x(active)} y1={M.top} y2={M.top + innerH} className="crosshair" />
                <line x1={M.left} x2={M.left + innerW} y1={y(shownPrice)} y2={y(shownPrice)} className="crosshair" />
                <circle cx={x(active)} cy={y(shownPrice)} r={4.5} fill={lineColor} stroke="var(--surface)" strokeWidth={2} />
                <rect x={M.left + innerW + 2} y={y(shownPrice) - 10} width={M.right - 4} height={20} rx={4} className="y-badge" />
                <text x={M.left + innerW + 8} y={y(shownPrice)} dy="0.32em" className="y-badge-text">
                  {compactPrice(shownPrice)}
                </text>
              </g>
            )}
          </svg>
        )}
      </div>
      <p className="chart-hint">Нажмите или проведите по графику, чтобы увидеть точную цену.</p>
    </div>
  );
}

/* ---------------- RSI и MACD ---------------- */

function Indicators({ s }: { s: Series }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const n = s.close.length;
  const w = Math.max(width, 10);
  const x = (i: number) => (n === 1 ? w / 2 : (i / (n - 1)) * w);
  const path = (vals: (number | null)[], y: (v: number) => number) => {
    let d = "";
    let on = false;
    vals.forEach((v, i) => {
      if (v === null) return void (on = false);
      d += `${on ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      on = true;
    });
    return d;
  };
  const yRsi = (v: number) => 6 + (1 - v / 100) * (IND_H - 12);
  const lastRsi = [...s.rsi].reverse().find((v) => v !== null) ?? null;
  const mVals = [...s.macd, ...s.signal, ...s.hist].filter((v): v is number => v !== null);
  const mB = Math.max(...mVals.map(Math.abs), 1e-9);
  const yM = (v: number) => IND_H / 2 - (v / mB) * (IND_H / 2 - 6);

  return (
    <div ref={ref} className="indicators">
      {width > 0 && (
        <>
          <div className="chart-legend">
            <span className="legend-item"><span className="swatch" style={{ background: "var(--accent)" }} />RSI 14</span>
            {lastRsi !== null && <span className="chart-current">{lastRsi.toFixed(1)}</span>}
            <span className="chart-meta-inline">30 / 70 — перепроданность / перекупленность</span>
          </div>
          <svg width={width} height={IND_H}>
            <line x1={0} x2={w} y1={yRsi(70)} y2={yRsi(70)} className="grid dashed" />
            <line x1={0} x2={w} y1={yRsi(30)} y2={yRsi(30)} className="grid dashed" />
            <path d={path(s.rsi, yRsi)} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
          </svg>
          <div className="chart-legend">
            <span className="legend-item"><span className="swatch" style={{ background: "var(--accent)" }} />MACD</span>
            <span className="legend-item"><span className="swatch" style={{ background: "var(--attn)" }} />Сигнальная</span>
          </div>
          <svg width={width} height={IND_H}>
            <line x1={0} x2={w} y1={yM(0)} y2={yM(0)} className="grid" />
            {s.hist.map((v, i) =>
              v === null ? null : (
                <rect
                  key={i}
                  x={x(i) - Math.max(w / n / 2 - 0.5, 0.5)}
                  y={v >= 0 ? yM(v) : yM(0)}
                  width={Math.max(w / n - 1, 1)}
                  height={Math.abs(yM(v) - yM(0))}
                  fill={v >= 0 ? "var(--gain)" : "var(--loss)"}
                  opacity={0.45}
                />
              )
            )}
            <path d={path(s.macd, yM)} fill="none" stroke="var(--accent)" strokeWidth={1.25} />
            <path d={path(s.signal, yM)} fill="none" stroke="var(--attn)" strokeWidth={1.25} />
          </svg>
        </>
      )}
    </div>
  );
}

/* ---------------- форматирование ---------------- */

const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

function parts(t: string) {
  // "2026-10-16" или "2026-10-16T09:35:00" — без перевода в часовой пояс браузера
  const [d, time = ""] = t.split("T");
  const [yy, mm, dd] = d.split("-").map(Number);
  return { yy, mm, dd, hhmm: time.slice(0, 5) };
}

function formatTick(t: string, intraday: boolean, firstT: string, lastT: string): string {
  const p = parts(t);
  if (intraday) return p.hhmm;
  const longRange = Date.parse(lastT) - Date.parse(firstT) > 120 * 864e5;
  if (longRange) return p.mm === 1 ? `${MONTHS[0]} ${String(p.yy).slice(2)}` : MONTHS[p.mm - 1];
  return `${p.dd} ${MONTHS[p.mm - 1]}`;
}

function formatFull(t: string, intraday: boolean): string {
  const p = parts(t);
  const date = `${p.dd} ${MONTHS[p.mm - 1]} ${p.yy}`;
  return intraday ? `${p.hhmm}, ${date}` : date;
}

function compactPrice(v: number): string {
  const abs = Math.abs(v);
  const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : 2;
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(v);
}

function xTickIndexes(n: number, count: number): number[] {
  if (n <= Math.max(count, 7)) return [...Array(n).keys()];
  const out = new Set<number>();
  for (let k = 0; k < count; k++) out.add(Math.round((k * (n - 1)) / (count - 1)));
  return [...out];
}
