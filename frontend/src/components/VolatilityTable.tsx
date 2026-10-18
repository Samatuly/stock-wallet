import type { PositionRisk } from "@/lib/api";
import { number } from "@/lib/format";

export default function VolatilityTable({ rows }: { rows: PositionRisk[] }) {
  return (
    <div className="volatility-block">
      <h3>Волатильность по позициям</h3>
      <p className="hint">
        Годовая, по дневным ценам за полгода. Показывает разброс, а не риск убытка напрямую —
        высокая волатильность бывает и у растущей бумаги.
      </p>
      <table className="volatility-table">
        <thead>
          <tr>
            <th>Акция</th>
            <th className="num">Волатильность</th>
            <th className="num">Точек истории</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticker}>
              <td className="ticker">{r.ticker}</td>
              <td className="num">
                {r.volatility_annualized === null ? "—" : `${number(r.volatility_annualized, 1)}%`}
              </td>
              <td className="num">
                {r.data_points}
                {r.volatility_annualized === null && r.data_points > 0 && (
                  <span className="hint-inline"> (мало данных)</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
