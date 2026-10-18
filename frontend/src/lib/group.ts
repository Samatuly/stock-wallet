import type { Valuation } from "@/lib/api";

/** Одна акция в портфеле: все покупки (лоты) одного тикера на одном рынке в одной валюте. */
export interface Holding {
  key: string;
  ticker: string;
  market: Valuation["market"];
  currency: string;
  lots: Valuation[]; // от новых к старым
  quantity: number;
  /** Средневзвешенная цена покупки: сумма(кол-во × цена) / сумма(кол-во). Комиссии не включены, как у брокеров. */
  avgPrice: number;
  cost: number; // потрачено всего, с комиссиями
  currentPrice: number | null;
  priceSource: string | null;
  priceIsManual: boolean;
  value: number | null;
  pnlAmount: number | null;
  pnlPercent: number | null;
  weightPercent: number | null;
  firstBuyDate: string;
  warnings: string[];
}

export function holdingKey(p: Pick<Valuation, "ticker" | "market" | "currency">): string {
  return `${p.ticker}|${p.market}|${p.currency}`;
}

/** Объединяет покупки одной акции. Порядок акций — как у первых встреченных лотов. */
export function groupPositions(positions: Valuation[]): Holding[] {
  const map = new Map<string, Valuation[]>();
  for (const p of positions) {
    const key = holdingKey(p);
    const list = map.get(key);
    if (list) list.push(p);
    else map.set(key, [p]);
  }

  return [...map.entries()].map(([key, lots]) => {
    const sorted = [...lots].sort((a, b) => (a.buy_date < b.buy_date ? 1 : a.buy_date > b.buy_date ? -1 : b.id - a.id));
    const first = sorted[0];
    const quantity = sum(sorted.map((l) => l.quantity));
    const spent = sum(sorted.map((l) => l.quantity * l.buy_price));
    const cost = sum(sorted.map((l) => l.cost));
    // Результат считаем, только если оценены ВСЕ лоты: иначе сумма вводила бы в заблуждение.
    const allValued = sorted.every((l) => l.value !== null && l.pnl_amount !== null);
    const value = allValued ? sum(sorted.map((l) => l.value as number)) : null;
    const pnlAmount = value === null ? null : value - cost;
    const weights = sorted.map((l) => l.weight_percent);
    const priced = sorted.find((l) => l.current_price !== null);

    return {
      key,
      ticker: first.ticker,
      market: first.market,
      currency: first.currency,
      lots: sorted,
      quantity,
      avgPrice: quantity > 0 ? spent / quantity : 0,
      cost,
      currentPrice: priced?.current_price ?? null,
      priceSource: priced?.price_source ?? null,
      priceIsManual: priced?.price_is_manual ?? false,
      value,
      pnlAmount,
      pnlPercent: pnlAmount !== null && cost > 0 ? (pnlAmount / cost) * 100 : null,
      weightPercent: weights.every((w) => w !== null) ? sum(weights as number[]) : null,
      firstBuyDate: sorted[sorted.length - 1].buy_date,
      warnings: [...new Set(sorted.map((l) => l.warning).filter((w): w is string => !!w))],
    };
  });
}

function sum(values: number[]): number {
  return values.reduce((a, b) => a + b, 0);
}
