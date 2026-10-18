import type { BenchmarkComparison } from "@/lib/api";
import { signedPercent, tone } from "@/lib/format";

export default function BenchmarkCard({ data }: { data: BenchmarkComparison | null }) {
  if (data === null) {
    return (
      <div className="card">
        <h3>Портфель против {`S&P 500`}</h3>
        <p className="empty">Пока недостаточно данных для сравнения.</p>
      </div>
    );
  }

  const ahead = data.portfolio_return_percent >= data.benchmark_return_percent;

  return (
    <div className="card">
      <h3>Портфель против {data.benchmark_name}</h3>
      <p className="hint">
        Доходность с {data.since_date}: ваш реальный результат против того, что было бы, если вложить
        те же суммы в {data.benchmark_name} в те же даты.
      </p>
      <div className="benchmark-row">
        <div className="benchmark-col">
          <span className="benchmark-label">Ваш портфель</span>
          <span className={`benchmark-value ${tone(data.portfolio_return_percent)}`}>
            {signedPercent(data.portfolio_return_percent)}
          </span>
        </div>
        <div className="benchmark-col">
          <span className="benchmark-label">{data.benchmark_name}</span>
          <span className={`benchmark-value ${tone(data.benchmark_return_percent)}`}>
            {signedPercent(data.benchmark_return_percent)}
          </span>
        </div>
      </div>
      <p className={`benchmark-verdict ${ahead ? "gain" : "loss"}`}>
        {ahead ? "Портфель обгоняет индекс" : "Портфель отстаёт от индекса"} на{" "}
        {signedPercent(data.portfolio_return_percent - data.benchmark_return_percent)}
      </p>
      {(data.skipped_tickers.length > 0 || data.missing_currencies.length > 0) && (
        <p className="hint-inline">
          {data.skipped_tickers.length > 0 && `Не учтены (нет истории индекса на дату покупки): ${data.skipped_tickers.join(", ")}. `}
          {data.missing_currencies.length > 0 && `Не удалось конвертировать: ${data.missing_currencies.join(", ")}.`}
        </p>
      )}
    </div>
  );
}
