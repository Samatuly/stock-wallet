"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type PriceAlert } from "@/lib/api";
import { number } from "@/lib/format";

const DISMISS_KEY = "stockwallet.dismissedAlerts";
const CHECK_EVERY_MS = 5 * 60 * 1000;

function readDismissed(): number[] {
  try {
    return JSON.parse(localStorage.getItem(DISMISS_KEY) ?? "[]");
  } catch {
    return [];
  }
}

// Проверка идёт, пока страница открыта: бэкенд сверяет алерты с ценами и помечает сработавшие.
// Сработавший алерт показывается сутки или пока его не закроют (закрытие хранится в браузере).
export default function AlertBanner() {
  const [fired, setFired] = useState<PriceAlert[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      try {
        await api.checkAlerts();
        const all = await api.alerts();
        const dismissed = readDismissed();
        const dayAgo = Date.now() - 24 * 3600 * 1000;
        const recent = all.filter(
          (a) => a.triggered_at && new Date(a.triggered_at + "Z").getTime() > dayAgo && !dismissed.includes(a.id)
        );
        if (!cancelled) setFired(recent);
      } catch {
        /* нет связи с бэкендом: ошибку уже покажет сама страница */
      }
    }
    void run();
    const timer = setInterval(run, CHECK_EVERY_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  function dismiss(id: number) {
    try {
      localStorage.setItem(DISMISS_KEY, JSON.stringify([...readDismissed(), id]));
    } catch {
      /* без хранилища закрытие действует до обновления страницы */
    }
    setFired((list) => list.filter((a) => a.id !== id));
  }

  if (fired.length === 0) return null;

  return (
    <section className="alert-banner" role="status">
      {fired.map((a) => (
        <div key={a.id} className="alert-banner-row">
          <span>
            <strong>{a.ticker}</strong> {a.direction === "above" ? "поднялась выше" : "упала ниже"}{" "}
            <span className="mono">{a.target_price}</span>: цена на момент срабатывания{" "}
            <span className="mono">{number(a.triggered_price, 2)}</span>
            {a.note ? ` (${a.note})` : ""}
          </span>
          <button className="link" onClick={() => dismiss(a.id)}>
            Закрыть
          </button>
        </div>
      ))}
      <Link href="/alerts" className="link-button">
        Все алерты →
      </Link>
    </section>
  );
}
