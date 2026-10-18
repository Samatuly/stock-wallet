"use client";

import { useEffect, useRef, useState } from "react";
import type { NewPosition, Valuation } from "@/lib/api";
import { SOURCE_LABEL, money, number, signedMoney, signedPercent, tone } from "@/lib/format";
import { groupPositions, type Holding } from "@/lib/group";
import PositionForm from "@/components/PositionForm";
import PriceChart from "@/components/PriceChart";

const MARKET_LABEL = { US: "США", EU: "Европа", KZ: "Казахстан" } as const;
const COLS = 8;

interface Props {
  positions: Valuation[];
  onDelete: (id: number) => Promise<void>;
  onSetPrice: (ticker: string, price: number, currency: string) => Promise<void>;
  onUpdate: (id: number, p: NewPosition) => Promise<void>;
  onAdd: (p: NewPosition) => Promise<void>;
}

export default function PositionTable({ positions, onDelete, onSetPrice, onUpdate, onAdd }: Props) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const holdings = groupPositions(positions);

  if (holdings.length === 0) {
    return (
      <p className="empty">
        Позиций пока нет. Нажмите «Добавить позицию» выше: тикер, количество, цену и дату.
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
            <th className="num">Ср. цена покупки</th>
            <th className="num">Цена сейчас</th>
            <th className="num">Стоимость</th>
            <th className="num">Результат</th>
            <th className="num">Доля</th>
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <HoldingRow
              key={h.key}
              h={h}
              open={openKey === h.key}
              onToggle={() => setOpenKey(openKey === h.key ? null : h.key)}
              onDelete={onDelete}
              onSetPrice={onSetPrice}
              onUpdate={onUpdate}
              onAdd={onAdd}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Panel = null | "add" | "price";

function HoldingRow({
  h,
  open,
  onToggle,
  onDelete,
  onSetPrice,
  onUpdate,
  onAdd,
}: { h: Holding; open: boolean; onToggle: () => void } & Omit<Props, "positions">) {
  const [panel, setPanel] = useState<Panel>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const needsPrice = h.currentPrice === null;
  const lotsLabel = h.lots.length === 1 ? h.lots[0].buy_date : `${h.lots.length} ${plural(h.lots.length, "покупка", "покупки", "покупок")}`;

  return (
    <>
      <tr className={`pos ${open ? "is-open" : ""}`}>
        <td className="first" data-label="">
          <button className="ticker-btn" onClick={onToggle} aria-expanded={open} title="Подробнее: график и история покупок">
            <span className={`market-dot ${h.market.toLowerCase()}`} aria-hidden="true" />
            <span className="ticker">{h.ticker}</span>
          </button>
          <div className="sub">
            {MARKET_LABEL[h.market]} · {lotsLabel}
          </div>
        </td>
        <td className="num" data-label="Количество">
          <div className="cell">{number(h.quantity, 4)}</div>
        </td>
        <td className="num" data-label="Ср. цена покупки">
          <div className="cell">{money(h.avgPrice, h.currency)}</div>
        </td>
        <td className="num" data-label="Цена сейчас">
          <div className="cell">
            {money(h.currentPrice, h.currency)}
            {h.priceSource && (
              <div className={`sub ${h.priceIsManual || h.priceSource === "cache-stale" ? "attn" : ""}`}>
                {SOURCE_LABEL[h.priceSource] ?? h.priceSource}
              </div>
            )}
          </div>
        </td>
        <td className="num" data-label="Стоимость">
          <div className="cell">{money(h.value, h.currency)}</div>
        </td>
        <td className={`num ${tone(h.pnlAmount)}`} data-label="Результат">
          <div className="cell">
            {signedMoney(h.pnlAmount, h.currency)}
            <div className="sub">{signedPercent(h.pnlPercent)}</div>
          </div>
        </td>
        <td className="num" data-label="Доля в портфеле">
          <div className="cell">{h.weightPercent === null ? "—" : `${number(h.weightPercent, 1)}%`}</div>
        </td>
        <td className="actions">
          <RowMenu>
            {(close) => (
              <>
                <button
                  onClick={() => {
                    if (!open) onToggle();
                    setHistoryOpen(true);
                    close();
                  }}
                >
                  История покупок
                </button>
                <button
                  onClick={() => {
                    setPanel(panel === "add" ? null : "add");
                    close();
                  }}
                >
                  Докупить
                </button>
                {!needsPrice && (
                  <button
                    onClick={() => {
                      setPanel(panel === "price" ? null : "price");
                      close();
                    }}
                  >
                    {h.priceIsManual ? "Изменить цену" : "Задать свою цену"}
                  </button>
                )}
              </>
            )}
          </RowMenu>
        </td>
      </tr>

      {(h.warnings.length > 0 || needsPrice || panel === "price") && (
        <tr className="note-row">
          <td colSpan={COLS}>
            {h.warnings.map((w) => (
              <span key={w} className="warning">
                {w}
              </span>
            ))}
            {(needsPrice || panel === "price") && (
              <ManualPriceForm
                ticker={h.ticker}
                currency={h.currency}
                onSubmit={async (price) => {
                  await onSetPrice(h.ticker, price, h.currency);
                  setPanel(null);
                }}
              />
            )}
          </td>
        </tr>
      )}

      {panel === "add" && (
        <tr className="note-row">
          <td colSpan={COLS}>
            <p className="panel-title">Новая покупка {h.ticker}</p>
            <PositionForm
              initial={{
                ticker: h.ticker,
                market: h.market,
                quantity: 0,
                buy_price: h.currentPrice ?? h.avgPrice,
                buy_date: new Date().toISOString().slice(0, 10),
                fee: 0,
                currency: h.currency,
                note: "",
              }}
              submitLabel="Добавить покупку"
              onCancel={() => setPanel(null)}
              onSubmit={async (data) => {
                await onAdd(data);
                setPanel(null);
              }}
            />
          </td>
        </tr>
      )}

      {open && (
        <tr className="note-row detail-row">
          <td colSpan={COLS}>
            <div className="detail-bar">
              <button
                type="button"
                className={`chip ${historyOpen ? "active" : ""}`}
                aria-expanded={historyOpen}
                onClick={() => setHistoryOpen((v) => !v)}
              >
                История покупок · {h.lots.length}
              </button>
            </div>
            {historyOpen && <LotHistory h={h} onDelete={onDelete} onUpdate={onUpdate} />}
            <PriceChart ticker={h.ticker} currency={h.currency} buyPrice={h.avgPrice} />
          </td>
        </tr>
      )}
    </>
  );
}

function LotHistory({
  h,
  onDelete,
  onUpdate,
}: { h: Holding } & Pick<Props, "onDelete" | "onUpdate">) {
  const [editingId, setEditingId] = useState<number | null>(null);

  return (
    <div className="lot-history">
      <table className="lots">
        <thead>
          <tr>
            <th>Дата</th>
            <th className="num">Кол-во</th>
            <th className="num">Цена</th>
            <th className="num">Сумма</th>
            <th className="num">Результат</th>
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {h.lots.map((l) => (
            <LotRow
              key={l.id}
              l={l}
              editing={editingId === l.id}
              onEdit={() => setEditingId(editingId === l.id ? null : l.id)}
              onDelete={onDelete}
              onUpdate={async (id, p) => {
                await onUpdate(id, p);
                setEditingId(null);
              }}
            />
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="foot-title">Итого</td>
            <td className="num" data-label="Кол-во">{number(h.quantity, 4)}</td>
            <td className="num" data-label="Средняя цена" title="Средневзвешенная цена">
              {money(h.avgPrice, h.currency)}
            </td>
            <td className="num" data-label="Вложено">{money(h.cost, h.currency)}</td>
            <td className={`num ${tone(h.pnlAmount)}`} data-label="Результат">
              {signedMoney(h.pnlAmount, h.currency)}
            </td>
            <td className="foot-empty" />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function LotRow({
  l,
  editing,
  onEdit,
  onDelete,
  onUpdate,
}: {
  l: Valuation;
  editing: boolean;
  onEdit: () => void;
} & Pick<Props, "onDelete" | "onUpdate">) {
  return (
    <>
      <tr>
        <td data-label="Дата">
          <div>
            {l.buy_date}
            {l.note && <div className="sub">{l.note}</div>}
          </div>
        </td>
        <td className="num" data-label="Кол-во">
          <div>{number(l.quantity, 4)}</div>
        </td>
        <td className="num" data-label="Цена">
          <div>{money(l.buy_price, l.currency)}</div>
        </td>
        <td className="num" data-label="Сумма">
          <div>
            {money(l.cost, l.currency)}
            {l.fee > 0 && <div className="sub">комиссия {money(l.fee, l.currency)}</div>}
          </div>
        </td>
        <td className={`num ${tone(l.pnl_amount)}`} data-label="Результат">
          <div>
            {signedMoney(l.pnl_amount, l.currency)}
            <div className="sub">{signedPercent(l.pnl_percent)}</div>
          </div>
        </td>
        <td className="lot-actions">
          <button type="button" className="link" onClick={onEdit}>
            {editing ? "Отмена" : "Изменить"}
          </button>
          <button
            type="button"
            className="link danger"
            onClick={() => {
              if (window.confirm(`Удалить покупку ${l.ticker} от ${l.buy_date}?`)) void onDelete(l.id);
            }}
          >
            Удалить
          </button>
        </td>
      </tr>
      {editing && (
        <tr className="lot-edit">
          <td colSpan={6}>
            <PositionForm
              initial={{
                ticker: l.ticker,
                market: l.market,
                quantity: l.quantity,
                buy_price: l.buy_price,
                buy_date: l.buy_date,
                fee: l.fee,
                currency: l.currency,
                note: l.note,
              }}
              submitLabel="Сохранить изменения"
              onCancel={onEdit}
              onSubmit={(data) => onUpdate(l.id, data)}
            />
          </td>
        </tr>
      )}
    </>
  );
}

function ManualPriceForm({
  ticker,
  currency,
  onSubmit,
}: {
  ticker: string;
  currency: string;
  onSubmit: (price: number) => Promise<void>;
}) {
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = Number(price.replace(",", "."));
    if (!(value > 0)) return;
    setBusy(true);
    try {
      await onSubmit(value);
      setPrice("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <label>
        <span className="sr-only">Цена {ticker}</span>
        <input inputMode="decimal" placeholder={`Цена, ${currency}`} value={price} onChange={(e) => setPrice(e.target.value)} />
      </label>
      <button type="submit" disabled={busy}>
        Задать цену
      </button>
    </form>
  );
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

// Одна кнопка «⋯» вместо нескольких ссылок в каждой строке: таблица становится спокойнее.
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
      <button type="button" className="icon-btn" aria-label="Действия с акцией" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
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
