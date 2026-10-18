"use client";

import AppHeader from "@/components/AppHeader";
import Link from "next/link";
import { useState } from "react";
import { api, type ImportResult } from "@/lib/api";
import { number } from "@/lib/format";

export default function ImportPage() {
  const [csvText, setCsvText] = useState<string | null>(null);
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(file: File | undefined) {
    setPreview(null);
    setDone(null);
    setError(null);
    if (!file) return;
    setFileName(file.name);
    try {
      const text = await file.text();
      setCsvText(text);
      setBusy(true);
      setPreview(await api.importCsv(text, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось прочитать файл");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!csvText) return;
    setBusy(true);
    setError(null);
    try {
      setDone(await api.importCsv(csvText, false));
      setPreview(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось импортировать");
    } finally {
      setBusy(false);
    }
  }

  const toAdd = preview ? preview.rows.filter((r) => !r.duplicate).length : 0;

  return (
    <main>
      <AppHeader title="Импорт из CSV" />

      <section className="card">
        <p className="hint">
          Загрузите CSV-файл (из Excel или отчёта брокера). В первой строке должны быть названия колонок:{" "}
          <strong>тикер, количество, цена покупки, дата</strong>. Необязательные: рынок (US/EU/KZ), валюта, комиссия,
          комментарий. Названия можно писать по-русски или по-английски (ticker, quantity, price, date). Даты лучше в формате
          ГГГГ-ММ-ДД или ДД.ММ.ГГГГ. Если рынок не указан, он определяется по тикеру (SAP.DE — Европа, KZTK.KZ — Казахстан,
          остальное — США). Позиции, которые уже есть в портфеле, пропускаются.
        </p>
        <input type="file" accept=".csv,text/csv,text/plain" onChange={(e) => onFile(e.target.files?.[0])} />
        {fileName && <p className="hint-inline">Файл: {fileName}</p>}
      </section>

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}
      {busy && <p className="empty">Обрабатываю…</p>}

      {preview && (
        <section className="card">
          <h2>Предпросмотр</h2>
          <p className="hint">
            Будет добавлено: <strong>{toAdd}</strong>. Уже есть в портфеле: {preview.skipped_duplicates}. Ошибок:{" "}
            {preview.errors.length}. Пока ничего не сохранено.
          </p>

          {preview.errors.length > 0 && (
            <ul className="import-errors">
              {preview.errors.map((e) => (
                <li key={e.line}>
                  Строка {e.line}: {e.message}
                </li>
              ))}
            </ul>
          )}

          {preview.rows.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Строка</th>
                    <th>Тикер</th>
                    <th>Рынок</th>
                    <th>Количество</th>
                    <th>Цена</th>
                    <th>Дата</th>
                    <th>Валюта</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.line} className={r.duplicate ? "row-muted" : ""}>
                      <td className="num">{r.line}</td>
                      <td>{r.ticker}</td>
                      <td>{r.market}</td>
                      <td className="num">{number(r.quantity, 4)}</td>
                      <td className="num">{number(r.buy_price, 4)}</td>
                      <td className="num">{r.buy_date}</td>
                      <td>{r.currency}</td>
                      <td>{r.duplicate ? "уже есть, пропущу" : "добавлю"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="form-actions">
            <button onClick={confirm} disabled={busy || toAdd === 0}>
              Добавить {toAdd} {toAdd === 1 ? "позицию" : "позиций"}
            </button>
            {preview.errors.length > 0 && toAdd > 0 && (
              <span className="hint-inline">Строки с ошибками будут пропущены, исправьте файл и загрузите его снова.</span>
            )}
          </div>
        </section>
      )}

      {done && (
        <section className="card">
          <h2>Готово</h2>
          <p>
            Добавлено позиций: <strong>{done.imported}</strong>. Пропущено как дубликаты: {done.skipped_duplicates}.
          </p>
          <Link href="/" className="link-button">
            Открыть портфель →
          </Link>
        </section>
      )}
    </main>
  );
}
