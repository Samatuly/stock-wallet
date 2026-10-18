import type { CurrencyTotal } from "@/lib/api";
import { money, signedMoney, signedPercent, tone } from "@/lib/format";

export default function Totals({ totals }: { totals: CurrencyTotal[] }) {
  if (totals.length === 0) return null;
  return (
    <section className="totals" aria-label="Итоги по валютам">
      {totals.map((t) =>
        t.priced_count === 0 ? (
          <div className="total" key={t.currency}>
            <div className="total-value muted">{t.currency}</div>
            <div className="total-meta">
              Нет цен по {t.unpriced_count} поз. Задайте цены вручную, чтобы увидеть итог.
            </div>
          </div>
        ) : (
        <div className="total" key={t.currency}>
          <div className="total-value">{money(t.value, t.currency)}</div>
          <div className={`total-pnl ${tone(t.pnl_amount)}`}>
            {signedMoney(t.pnl_amount, t.currency)} · {signedPercent(t.pnl_percent)}
          </div>
          <div className="total-meta">
            Вложено {money(t.cost, t.currency)}. Позиций с ценой: {t.priced_count}
            {t.unpriced_count > 0 ? `, без цены: ${t.unpriced_count}` : ""}
          </div>
        </div>
        ),
      )}
    </section>
  );
}
