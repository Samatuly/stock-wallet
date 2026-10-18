"use client";

import { useState } from "react";
import type { Market, NewPosition } from "@/lib/api";

const DEFAULT_CURRENCY: Record<Market, string> = { US: "USD", EU: "EUR", KZ: "KZT" };
const TICKER_HINT: Record<Market, string> = {
  US: "Например, AAPL",
  EU: "С суффиксом биржи, например SAP.DE",
  KZ: "Бумаги с зарубежным листингом, например KSPI; остальные с ценой вручную",
};

const today = () => new Date().toISOString().slice(0, 10);

interface Props {
  initial?: NewPosition;
  submitLabel: string;
  onSubmit: (p: NewPosition) => Promise<void>;
  onCancel?: () => void;
}

export default function PositionForm({ initial, submitLabel, onSubmit, onCancel }: Props) {
  const [market, setMarket] = useState<Market>(initial?.market ?? "US");
  const [ticker, setTicker] = useState(initial?.ticker ?? "");
  const [quantity, setQuantity] = useState(initial ? String(initial.quantity) : "");
  const [buyPrice, setBuyPrice] = useState(initial ? String(initial.buy_price) : "");
  const [buyDate, setBuyDate] = useState(initial?.buy_date ?? today());
  const [fee, setFee] = useState(initial && initial.fee ? String(initial.fee) : "");
  const [currency, setCurrency] = useState(initial?.currency ?? "USD");
  const [currencyTouched, setCurrencyTouched] = useState(Boolean(initial));
  const [note, setNote] = useState(initial?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const num = (s: string) => Number(s.replace(",", "."));

  function changeMarket(m: Market) {
    setMarket(m);
    if (!currencyTouched) setCurrency(DEFAULT_CURRENCY[m]);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!ticker.trim()) return setError("Укажите тикер");
    if (!(num(quantity) > 0)) return setError("Количество должно быть больше нуля");
    if (!(num(buyPrice) > 0)) return setError("Цена покупки должна быть больше нуля");
    setBusy(true);
    try {
      await onSubmit({
        ticker: ticker.trim().toUpperCase(),
        market,
        quantity: num(quantity),
        buy_price: num(buyPrice),
        buy_date: buyDate,
        fee: fee ? num(fee) : 0,
        currency: currency.trim().toUpperCase(),
        note: note.trim(),
      });
      if (!initial) {
        setTicker("");
        setQuantity("");
        setBuyPrice("");
        setFee("");
        setNote("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить позицию");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="add-form" onSubmit={submit}>
      <div className="grid">
        <label>
          Рынок
          <select value={market} onChange={(e) => changeMarket(e.target.value as Market)}>
            <option value="US">США</option>
            <option value="EU">Европа</option>
            <option value="KZ">Казахстан</option>
          </select>
        </label>
        <label>
          Тикер
          <input value={ticker} onChange={(e) => setTicker(e.target.value)} autoCapitalize="characters" />
          <small>{TICKER_HINT[market]}</small>
        </label>
        <label>
          Количество
          <input inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        </label>
        <label>
          Цена покупки за акцию
          <input inputMode="decimal" value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} />
        </label>
        <label>
          Дата покупки
          <input type="date" value={buyDate} max={today()} onChange={(e) => setBuyDate(e.target.value)} />
        </label>
        <label>
          Комиссия брокера
          <input inputMode="decimal" value={fee} placeholder="0" onChange={(e) => setFee(e.target.value)} />
        </label>
        <label>
          Валюта
          <input
            value={currency}
            maxLength={8}
            onChange={(e) => {
              setCurrency(e.target.value);
              setCurrencyTouched(true);
            }}
          />
        </label>
        <label className="wide">
          Заметка: почему купили
          <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
        </label>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="form-actions">
        <button type="submit" disabled={busy}>
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
            Отмена
          </button>
        )}
      </div>
    </form>
  );
}
