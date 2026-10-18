import type { Valuation } from "@/lib/api";
import { signedPercent, tone } from "@/lib/format";

export default function RankedPositions({ title, positions }: { title: string; positions: Valuation[] }) {
  return (
    <div className="ranked-block">
      <h3>{title}</h3>
      {positions.length === 0 ? (
        <p className="empty">Недостаточно позиций, чтобы выделить отдельно</p>
      ) : (
        <ul className="ranked-list">
          {positions.map((p) => (
            <li key={p.id}>
              <span className="ticker">{p.ticker}</span>
              <span className={tone(p.pnl_percent)}>{signedPercent(p.pnl_percent)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
