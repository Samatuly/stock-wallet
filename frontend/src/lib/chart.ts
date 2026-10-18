export type PeriodKey = "1D" | "7D" | "1M" | "6M" | "1Y";

export const PERIODS: { key: PeriodKey; label: string; days: number }[] = [
  { key: "1D", label: "1Д", days: 1 },
  { key: "7D", label: "7Д", days: 7 },
  { key: "1M", label: "1М", days: 30 },
  { key: "6M", label: "6М", days: 182 },
  { key: "1Y", label: "1Г", days: 365 },
];

/** Первая дата периода (включительно), отсчитанная от последней даты ряда "ГГГГ-ММ-ДД". */
export function periodStart(lastDate: string, period: PeriodKey): string {
  const days = PERIODS.find((p) => p.key === period)?.days ?? 365;
  const d = new Date(`${lastDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/** «Красивые» деления оси: шаг 1, 2, 2.5 или 5 × 10^k, примерно count штук, покрывают [min, max]. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!(max > min)) return [min];
  const raw = (max - min) / Math.max(count - 1, 1);
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? 10 * pow;
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}
