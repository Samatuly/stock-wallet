"use client";

import AppHeader from "@/components/AppHeader";
import Link from "next/link";
import { useState } from "react";
import { api, type ImportResult } from "@/lib/api";
import { number } from "@/lib/format";

// Шаблон с разделителем «;» и BOM: так русский Excel открывает его сразу по колонкам и без «кракозябр».
const TEMPLATE_ROWS = [
  ["тикер", "количество", "цена покупки", "дата", "рынок", "валюта", "комиссия", "комментарий"],
  ["AAPL", "10", "172,40", "15.03.2025", "US", "USD", "1", "Первая покупка"],
  ["AAPL", "5", "189,90", "20.06.2025", "US", "USD", "1", "Докупил на просадке"],
  ["SAP.DE", "8", "172,00", "02.04.2025", "EU", "EUR", "2,5", ""],
  ["KSPI", "3", "95,10", "10.01.2025", "US", "USD", "0", "Kaspi на Nasdaq"],
];

function downloadTemplate() {
  const csv = "\uFEFF" + TEMPLATE_ROWS.map((r) => r.join(";")).join("\r\n") + "\r\n";
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "stock-wallet-шаблон.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

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
        <div className="template-box">
          <div className="template-head">
            <div>
              <strong>Готовый шаблон</strong>
              <p className="hint-inline">Скачайте, откройте в Excel или Google Таблицах, замените примеры своими покупками и сохраните как CSV.</p>
            </div>
            <button type="button" className="btn-primary" onClick={downloadTemplate}>
              Скачать шаблон CSV
            </button>
          </div>
          <div className="table-wrap">
            <table className="template-table">
              <thead>
                <tr>
                  {TEMPLATE_ROWS[0].map((h, i) => (
                    <th key={h}>
                      {h}
                      {i < 4 && <span className="req" title="обязательно">*</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {TEMPLATE_ROWS.slice(1, 3).map((r, i) => (
                  <tr key={i}>
                    {r.map((c, j) => (
                      <td key={j}>{c}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint-inline">* обязательные колонки. Несколько покупок одной акции — отдельными строками, в портфеле они объединятся.</p>
        </div>

        <label className="file-label">
          <span>Загрузить заполненный файл</span>
          <input type="file" accept=".csv,text/csv,text/plain" onChange={(e) => onFile(e.target.files?.[0])} />
        </label>
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
