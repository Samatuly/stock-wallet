import type { AllocationItem } from "@/lib/api";
import { money, number } from "@/lib/format";

const MARKET_LABEL: Record<string, string> = { US: "США", EU: "Европа", KZ: "Казахстан" };

export default function AllocationBars({
  title,
  items,
  currency,
  labelMap,
}: {
  title: string;
  items: AllocationItem[];
  currency: string;
  labelMap?: Record<string, string>;
}) {
  return (
    <div className="allocation-block">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="empty">Нет данных</p>
      ) : (
        <ul className="allocation-list">
          {items.map((item) => (
            <li key={item.label}>
              <div className="allocation-row">
                <span className="allocation-label">{labelMap?.[item.label] ?? item.label}</span>
                <span className="allocation-value">
                  {money(item.value, currency)} · {number(item.percent, 1)}%
                </span>
              </div>
              <div className="allocation-bar">
                <div className="allocation-bar-fill" style={{ width: `${Math.min(item.percent, 100)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export { MARKET_LABEL };
