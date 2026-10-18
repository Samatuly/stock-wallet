"use client";

import { useCallback, useEffect, useState } from "react";
import AddPositionForm from "@/components/AddPositionForm";
import CombinedTotal from "@/components/CombinedTotal";
import PositionTable from "@/components/PositionTable";
import Totals from "@/components/Totals";
import AppHeader from "@/components/AppHeader";
import Collapsible from "@/components/Collapsible";
import AlertBanner from "@/components/AlertBanner";
import { api, type NewPosition, type Portfolio } from "@/lib/api";

export default function Home() {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayCurrency, setDisplayCurrency] = useState("USD");

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

      <section className="card">
        {data ? (
          <PositionTable positions={data.positions} onDelete={remove} onSetPrice={setPrice} onUpdate={update} />
        ) : (
          !error && <p className="empty">Загружаю портфель…</p>
        )}
      </section>

      <section className="card card-flush">
        <Collapsible title="Добавить позицию" hint="тикер, количество, цена, дата">
          <AddPositionForm onAdd={add} />
        </Collapsible>
      </section>

      <footer>
        Данные информационные и не являются инвестиционной рекомендацией.
      </footer>
    </main>
  );
}
