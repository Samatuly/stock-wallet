"use client";

import { useEffect, useState } from "react";
import { api, type Fundamentals } from "@/lib/api";
import { number } from "@/lib/format";

export default function FundamentalsStrip({ ticker }: { ticker: string }) {
  const [data, setData] = useState<Fundamentals | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .fundamentals(ticker)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Не удалось загрузить");
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (error) return null; // необязательные данные — молча не показываем, если недоступны
  if (data === null) return <p className="empty fundamentals-loading">Загружаю фундаментальные данные…</p>;

  const nothing = data.pe_ratio === null && data.dividend_yield === null && data.next_earnings_date === null;
  if (nothing) return null;

  return (
    <div className="fundamentals-strip">
      <div className="fundamentals-item">
        <span className="fundamentals-label">P/E</span>
        <span className="fundamentals-value">{data.pe_ratio === null ? "—" : number(data.pe_ratio, 1)}</span>
      </div>
      <div className="fundamentals-item">
        <span className="fundamentals-label">Див. доходность</span>
        <span className="fundamentals-value">
          {data.dividend_yield === null ? "—" : `${number(data.dividend_yield, 2)}%`}
        </span>
      </div>
      <div className="fundamentals-item">
        <span className="fundamentals-label">Ближайший отчёт</span>
        <span className="fundamentals-value">{data.next_earnings_date ?? "—"}</span>
      </div>
      {data.is_stale && <span className="hint-inline">данные устарели</span>}
    </div>
  );
}
