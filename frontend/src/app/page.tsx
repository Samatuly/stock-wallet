"use client";

import { useCallback, useEffect, useState } from "react";
import AddPositionForm from "@/components/AddPositionForm";
import Link from "next/link";
import CombinedTotal from "@/components/CombinedTotal";
import PositionTable from "@/components/PositionTable";
import Totals from "@/components/Totals";
import AppHeader from "@/components/AppHeader";
import AlertBanner from "@/components/AlertBanner";
import { api, type NewPosition, type Portfolio } from "@/lib/api";

export default function Home() {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayCurrency, setDisplayCurrency] = useState("USD");
  const [adding, setAdding] = useState(false);

  const load = useCallback(
    async (refresh = false) => {
      setLoading(true);
      try {
        setData(await api.portfolio(refresh, displayCurrency));
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Не удалось загрузить портфель");
      } finally {
        setLoading(false);
      }
    },
    [displayCurrency]
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function add(p: NewPosition) {
    await api.addPosition(p);
    await load();
  }

  async function addFromTopForm(p: NewPosition) {
    await add(p);
    setAdding(false);
  }

  async function update(id: number, p: NewPosition) {
    await api.updatePosition(id, p);
    await load();
  }

  async function remove(id: number) {
    try {
      await api.deletePosition(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось удалить позицию");
    }
  }

  async function setPrice(ticker: string, price: number, currency: string) {
    try {
      await api.setManualPrice(ticker, price, currency);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить цену");
    }
  }

  return (
    <main>
      <AppHeader
        title="Портфель"
        actions={
          <button onClick={() => load(true)} disabled={loading}>
            {loading ? "Загрузка…" : "Обновить цены"}
          </button>
        }
      />

      <AlertBanner />

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}

      <CombinedTotal data={data?.combined ?? null} current={displayCurrency} onChange={setDisplayCurrency} />

      {data && data.totals.length > 1 && (
        <details className="by-currency">
          <summary>По валютам отдельно</summary>
          <Totals totals={data.totals} />
        </details>
      )}

      <div className="positions-toolbar">
        <button type="button" className="btn-primary" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M7 1.5v11M1.5 7h11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          {adding ? "Закрыть" : "Добавить позицию"}
        </button>
        <Link href="/import" className="toolbar-link">
          Импорт из CSV
        </Link>
      </div>

      {adding && (
        <section className="card add-card">
          <AddPositionForm onAdd={addFromTopForm} />
        </section>
      )}

      <section className="card">
        {data ? (
          <PositionTable
            positions={data.positions}
            onDelete={remove}
            onSetPrice={setPrice}
            onUpdate={update}
            onAdd={add}
          />
        ) : (
          !error && <p className="empty">Загружаю портфель…</p>
        )}
      </section>

      <footer>
        Данные информационные и не являются инвестиционной рекомендацией.
      </footer>
    </main>
  );
}
