"use client";

import AppHeader from "@/components/AppHeader";
import { useCallback, useEffect, useState } from "react";
import { api, type JournalAction, type JournalEntry, type Market } from "@/lib/api";
import { number, signedPercent, tone } from "@/lib/format";

const ACTION_LABEL: Record<JournalAction, string> = {
  buy: "Покупка",
  sell: "Продажа",
  hold: "Держу",
  watch: "Наблюдаю",
};

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ticker, setTicker] = useState("");
  const [market, setMarket] = useState<Market>("US");
  const [action, setAction] = useState<JournalAction>("buy");
  const [reason, setReason] = useState("");
  const [expectation, setExpectation] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setEntries(await api.journal());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить журнал");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) {
      setError("Укажите тикер");
      return;
    }
    setBusy(true);
    try {
      await api.addJournal({ ticker, market, action, reason, expectation });
      setTicker("");
      setReason("");
      setExpectation("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить запись");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!confirm("Удалить запись?")) return;
    try {
      await api.deleteJournal(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить запись");
    }
  }

  return (
    <main>
      <AppHeader title="Журнал решений" />

      <section className="card">
        <p className="hint">
          Записывайте, что решили по акции и почему. Цена в момент записи сохраняется автоматически, поэтому позже видно,
          чем закончилось решение и совпало ли оно с ожиданием.
        </p>
        <form className="add-form" onSubmit={submit}>
          <div className="grid">
            <label>
              Решение
              <select value={action} onChange={(e) => setAction(e.target.value as JournalAction)}>
                {(Object.keys(ACTION_LABEL) as JournalAction[]).map((a) => (
                  <option key={a} value={a}>
                    {ACTION_LABEL[a]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Рынок
              <select value={market} onChange={(e) => setMarket(e.target.value as Market)}>
                <option value="US">США</option>
                <option value="EU">Европа</option>
                <option value="KZ">Казахстан</option>
              </select>
            </label>
            <label>
              Тикер
              <input value={ticker} onChange={(e) => setTicker(e.target.value)} autoCapitalize="characters" />
            </label>
            <label className="wide">
              Почему
              <textarea rows={3} value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} />
            </label>
            <label className="wide">
              Чего жду и к какому сроку
              <input value={expectation} maxLength={500} onChange={(e) => setExpectation(e.target.value)} />
            </label>
          </div>
          <div className="form-actions">
            <button type="submit" disabled={busy}>
              Записать решение
            </button>
          </div>
        </form>
      </section>

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}
      {!entries && !error && <p className="empty">Загружаю журнал…</p>}
      {entries && entries.length === 0 && <p className="empty">Записей пока нет. Добавьте первое решение выше.</p>}

      {entries && entries.length > 0 && (
        <section className="journal-list">
          {entries.map((en) => (
            <article key={en.id} className="card journal-entry">
              <div className="journal-head">
                <span>
                  <strong>{en.ticker}</strong> · {ACTION_LABEL[en.action]}
                </span>
                <span className="hint-inline">{new Date(en.created_at + "Z").toLocaleDateString("ru-RU")}</span>
              </div>
              {en.reason && <p className="journal-reason">{en.reason}</p>}
              {en.expectation && <p className="hint-inline">Ожидание: {en.expectation}</p>}
              <div className="journal-prices">
                <span>
                  Цена тогда: <strong className="mono">{number(en.price_at_entry, 2)}</strong>
                </span>
                <span>
                  Сейчас: <strong className="mono">{number(en.current_price, 2)}</strong>
                </span>
                <span className={tone(en.change_percent)}>
                  С тех пор: <strong className="mono">{signedPercent(en.change_percent)}</strong>
                </span>
                <button className="link" onClick={() => remove(en.id)}>
                  Удалить
                </button>
              </div>
              {en.price_at_entry === null && (
                <p className="hint-inline">Цену в момент записи получить не удалось, сравнение недоступно.</p>
              )}
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
