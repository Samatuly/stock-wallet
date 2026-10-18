"use client";

import type { CombinedTotal as CombinedTotalData } from "@/lib/api";
import { money, signedMoney, signedPercent, tone } from "@/lib/format";

const CURRENCIES = ["USD", "EUR", "KZT", "GBP"] as const;
const CURRENCY_LABEL: Record<string, string> = {
  USD: "Доллар",
  EUR: "Евро",
  KZT: "Тенге",
  GBP: "Фунт",
};

interface Props {
  data: CombinedTotalData | null;
  current: string;
  onChange: (currency: string) => void;
}

export default function CombinedTotal({ data, current, onChange }: Props) {
  const options = CURRENCIES.includes(current as (typeof CURRENCIES)[number])
    ? CURRENCIES
    : [current, ...CURRENCIES];

  return (
    <section className="combined" aria-label="Общая стоимость портфеля">
      <div className="currency-switch" role="group" aria-label="Валюта отображения">
        {options.map((c) => (
          <button
            key={c}
            type="button"
            className={c === current ? "active" : ""}
            onClick={() => onChange(c)}
            title={CURRENCY_LABEL[c] ?? c}
          >
            {c}
          </button>
        ))}
      </div>

      {data && (
        <>
          <div className="combined-value">{money(data.value, data.currency)}</div>
          <div className={`combined-pnl ${tone(data.pnl_amount)}`}>
            {signedMoney(data.pnl_amount, data.currency)} · {signedPercent(data.pnl_percent)}
          </div>
          <div className="combined-meta">
            {data.rate_date ? `Курс на ${data.rate_date}` : "Курс недоступен"}
            {data.is_stale && " · курс устарел"}
            {data.missing_currencies.length > 0 &&
              ` · не удалось конвертировать: ${data.missing_currencies.join(", ")}`}
          </div>
        </>
      )}
    </section>
  );
}
