"use client";

import { useEffect, useRef, useState } from "react";
import type { NewPosition, Valuation } from "@/lib/api";
import { SOURCE_LABEL, money, number, signedMoney, signedPercent, tone } from "@/lib/format";
import PositionForm from "@/components/PositionForm";
import PriceChart from "@/components/PriceChart";

const MARKET_LABEL = { US: "США", EU: "Европа", KZ: "Казахстан" } as const;

interface Props {
  positions: Valuation[];
  onDelete: (id: number) => Promise<void>;
  onSetPrice: (ticker: string, price: number, currency: string) => Promise<void>;
  onUpdate: (id: number, p: NewPosition) => Promise<void>;
}

export default function PositionTable({ positions, onDelete, onSetPrice, onUpdate }: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [chartTicker, setChartTicker] = useState<string | null>(null);

  if (positions.length === 0) {
    return (
      <p className="empty">
        Позиций пока нет. Добавьте первую покупку ниже: тикер, количество, цену и дату.
      </p>
    );
  }
  return (
    <div className="table-wrap positions">
      <table>
        <thead>
          <tr>
            <th>Акция</th>
            <th className="num">Кол-во</th>
            <th className="num">Цена покупки</th>
            <th className="num">Цена сейчас</th>
            <th className="num">Стоимость</th>
            <th className="num">Результат</th>
            <th className="num">Доля</th>
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <Row
              key={p.id}
              p={p}
              onDelete={onDelete}
              onSetPrice={onSetPrice}
              onUpdate={onUpdate}
              editing={editingId === p.id}
              onToggleEdit={() => setEditingId(editingId === p.id ? null : p.id)}
              chartOpen={chartTicker === p.ticker}
              onToggleChart={() => setChartTicker(chartTicker === p.ticker ? null : p.ticker)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface RowProps {
  p: Valuation;
  editing: boolean;
  onToggleEdit: () => void;
  chartOpen: boolean;
  onToggleChart: () => void;
}

function Row({
  p,
  onDelete,
  onSetPrice,
  onUpdate,
  editing,
  onToggleEdit,
  chartOpen,
  onToggleChart,
}: RowProps & Omit<Props, "positions">) {
  const [priceEditing, setPriceEditing] = useState(false);
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const needsPrice = p.current_price === null;
  const showPriceForm = needsPrice || priceEditing;

  async function submitPrice(e: React.FormEvent) {
    e.preventDefault();
    const value = Number(price.replace(",", "."));
    if (!(value > 0)) return;
    setBusy(true);
    try {
      await onSetPrice(p.ticker, value, p.currency);
      setPriceEditing(false);
      setPrice("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <tr className="pos">
        <td className="first" data-label="">
          <button className="ticker-btn" onClick={onToggleChart} title="Показать график цены">
            <span className={`market-dot ${p.market.toLowerCase()}`} aria-hidden="true" />
            <span className="ticker">{p.ticker}</span>
          </button>
          <div className="sub">{MARKET_LABEL[p.market]} · {p.buy_date}</div>
        </td>
        <td className="num" data-label="Количество">
          <div className="cell">{number(p.quantity, 4)}</div>
        </td>
        <td className="num" data-label="Цена покупки">
          <div className="cell">{money(p.buy_price, p.currency)}</div>
        </td>
        <td className="num" data-label="Цена сейчас">
          <div className="cell">
            {money(p.current_price, p.currency)}
            {p.price_source && (
              <div className={`sub ${p.price_is_manual || p.price_source === "cache-stale" ? "attn" : ""}`}>
                {SOURCE_LABEL[p.price_source] ?? p.price_source}
              </div>
            )}
          </div>
        </td>
        <td className="num" data-label="Стоимость">
          <div className="cell">{money(p.value, p.currency)}</div>
        </td>
        <td className={`num ${tone(p.pnl_amount)}`} data-label="Результат">
          <div className="cell">
            {signedMoney(p.pnl_amount, p.currency)}
            <div className="sub">{signedPercent(p.pnl_percent)}</div>
          </div>
        </td>
        <td className="num" data-label="Доля в портфеле">
          <div className="cell">{p.weight_percent === null ? "—" : `${number(p.weight_percent, 1)}%`}</div>
        </td>
        <td className="actions">
          <RowMenu>
            {(close) => (
              <>
                {!needsPrice && (
                  <button
                    onClick={() => {
                      setPriceEditing((v) => !v);
                      close();
                    }}
                  >
                    {p.price_is_manual ? "Изменить цену" : "Задать свою цену"}
                  </button>
                )}
                <button
                  onClick={() => {
                    onToggleEdit();
                    close();
                  }}
                >
                  Изменить позицию
                </button>
                <button
                  className="danger"
                  onClick={() => {
                    close();
                    if (window.confirm(`Удалить позицию ${p.ticker} от ${p.buy_date}?`)) void onDelete(p.id);
                  }}
                >
                  Удалить
                </button>
              </>
            )}
          </RowMenu>
        </td>
      </tr>

      {chartOpen && (
        <tr className="note-row">
          <td colSpan={8}>
            <PriceChart ticker={p.ticker} currency={p.currency} buyPrice={p.buy_price} />
          </td>
        </tr>
      )}

      {editing && (
        <tr className="note-row">
          <td colSpan={8}>
            <PositionForm
              initial={{
                ticker: p.ticker,
                market: p.market,
                quantity: p.quantity,
                buy_price: p.buy_price,
                buy_date: p.buy_date,
                fee: p.fee,
                currency: p.currency,
                note: p.note,
              }}
              submitLabel="Сохранить изменения"
              onCancel={onToggleEdit}
              onSubmit={async (data) => {
                await onUpdate(p.id, data);
                onToggleEdit();
              }}
            />
          </td>
        </tr>
      )}

      {(p.warning || showPriceForm) && (
        <tr className="note-row">
          <td colSpan={8}>
            {p.warning && <span className="warning">{p.warning}</span>}
            {showPriceForm && (
              <form className="inline-form" onSubmit={submitPrice}>
                <label>
                  <span className="sr-only">Цена {p.ticker}</span>
                  <input
                    inputMode="decimal"
                    placeholder={`Цена, ${p.currency}`}
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                  />
                </label>
                <button type="submit" disabled={busy}>
                  Задать цену
                </button>
              </form>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// Одна кнопка «⋯» вместо трёх ссылок в каждой строке: таблица становится спокойнее.
function RowMenu({ children }: { children: (close: () => void) => React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="row-menu" ref={ref}>
      <button type="button" className="icon-btn" aria-label="Действия с позицией" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          <circle cx="4" cy="9" r="1.5" fill="currentColor" />
          <circle cx="9" cy="9" r="1.5" fill="currentColor" />
          <circle cx="14" cy="9" r="1.5" fill="currentColor" />
        </svg>
      </button>
      {open && <div className="row-menu-pop" role="menu">{children(() => setOpen(false))}</div>}
    </div>
  );
}
