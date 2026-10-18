"use client";

import AppHeader from "@/components/AppHeader";
import { useCallback, useEffect, useState } from "react";
import { api, type Market, type PriceAlert } from "@/lib/api";
import { number } from "@/lib/format";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<PriceAlert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ticker, setTicker] = useState("");
  const [market, setMarket] = useState<Market>("US");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      await api.checkAlerts();
      setAlerts(await api.alerts());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить алерты");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = Number(target.replace(",", "."));
    if (!ticker.trim() || !(value > 0)) {
      setError("Укажите тикер и положительную целевую цену");
      return;
    }
    setBusy(true);
    try {
      await api.addAlert({ ticker, market, direction, target_price: value, note });
      setTicker("");
      setTarget("");
      setNote("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать алерт");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteAlert(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить алерт");
    }
  }

  const active = alerts?.filter((a) => a.active) ?? [];
  const fired = alerts?.filter((a) => !a.active) ?? [];

  return (
    <main>
      <AppHeader title="Алерты по цене" />

      <section className="card">
        <p className="hint">
          Алерт срабатывает один раз, когда цена поднимается выше или опускается ниже заданного уровня. Проверка идёт, пока
          приложение открыто в браузере (при загрузке страницы и раз в 5 минут). Когда приложение закрыто, проверки нет,
          а уведомлений на телефон пока нет.
        </p>
        <form className="add-form" onSubmit={submit}>
          <div className="grid">
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
            <label>
              Условие
              <select value={direction} onChange={(e) => setDirection(e.target.value as "above" | "below")}>
                <option value="above">Цена выше</option>
                <option value="below">Цена ниже</option>
              </select>
            </label>
            <label>
              Целевая цена
              <input inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
            </label>
            <label className="wide">
              Заметка (необязательно)
              <input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
            </label>
          </div>
          <div className="form-actions">
            <button type="submit" disabled={busy}>
              Создать алерт
            </button>
          </div>
        </form>
      </section>

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}
      {!alerts && !error && <p className="empty">Загружаю алерты…</p>}

      {alerts && (
        <>
          <section className="card">
            <h2>Активные</h2>
            {active.length === 0 ? (
              <p className="empty">Активных алертов нет.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Тикер</th>
                      <th>Условие</th>
                      <th>Цель</th>
                      <th>Сейчас</th>
                      <th>Заметка</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {active.map((a) => (
                      <tr key={a.id}>
                        <td>{a.ticker}</td>
                        <td>{a.direction === "above" ? "выше" : "ниже"}</td>
                        <td className="num">{number(a.target_price, 2)}</td>
                        <td className="num">{a.current_price !== null ? number(a.current_price, 2) : "нет цены"}</td>
                        <td>{a.note}</td>
                        <td>
                          <button className="link" onClick={() => remove(a.id)}>
                            Удалить
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {fired.length > 0 && (
            <section className="card">
              <h2>Сработавшие</h2>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Тикер</th>
                      <th>Условие</th>
                      <th>Цель</th>
                      <th>Цена при срабатывании</th>
                      <th>Когда</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {fired.map((a) => (
                      <tr key={a.id}>
                        <td>{a.ticker}</td>
                        <td>{a.direction === "above" ? "выше" : "ниже"}</td>
                        <td className="num">{number(a.target_price, 2)}</td>
                        <td className="num">{number(a.triggered_price, 2)}</td>
                        <td className="num">{a.triggered_at ? new Date(a.triggered_at + "Z").toLocaleString("ru-RU") : "—"}</td>
                        <td>
                          <button className="link" onClick={() => remove(a.id)}>
                            Удалить
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
