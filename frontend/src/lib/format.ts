export function money(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return "—";
  try {
    return new Intl.NumberFormat("ru-RU", { style: "currency", currency }).format(value);
  } catch {
    // Нестандартный код валюты (например, GBp)
    return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value)} ${currency}`;
  }
}

export function number(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(value);
}

export function signedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Math.abs(value))}%`;
}

export function signedMoney(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${money(Math.abs(value), currency)}`;
}

export function tone(value: number | null | undefined): "gain" | "loss" | "flat" {
  if (value === null || value === undefined || value === 0) return "flat";
  return value > 0 ? "gain" : "loss";
}

export const SOURCE_LABEL: Record<string, string> = {
  finnhub: "Finnhub",
  yfinance: "Yahoo",
  tradernet: "Freedom",
  manual: "вручную",
  "cache-stale": "устарела",
};
