import { useState } from "react";
import { api } from "../api/client";
import type { Transaction, UploadResult } from "../api/types";
import { formatCurrency, formatNumber } from "../utils/format";

interface Props {
  transactions: Transaction[];
  onChanged: () => void;
}

export function TransactionsPanel({ transactions, onChanged }: Props) {
  return (
    <div>
      <LedgerControls onChanged={onChanged} />
      <LedgerTable transactions={transactions} />
    </div>
  );
}

function LedgerControls({ onChanged }: { onChanged: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState<"upload" | "sync" | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy("upload");
    setError(null);
    setResult(null);
    setMessage(null);
    try {
      const res = await api.uploadTransactions(file, undefined, replace);
      setResult(res);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function sync() {
    setBusy("sync");
    setError(null);
    setMessage(null);
    try {
      const res = await api.syncHoldings();
      setMessage(
        `Rebuilt ${res.holdings_created} holding parcel(s) from ${res.tickers.length} ticker(s).`,
      );
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="manage-grid" style={{ marginBottom: "1.5rem" }}>
      <form className="chart-card" onSubmit={upload}>
        <h3>Import transactions (CSV)</h3>
        <p className="muted small">
          Columns: ticker, type (buy/sell), quantity, price_per_unit, trade_date,
          and optional exchange, fee, reference, currency.
        </p>
        <label className="field">
          <span>CSV file</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={replace}
            onChange={(e) => setReplace(e.target.checked)}
          />
          <span>Replace existing transactions</span>
        </label>
        <button type="submit" disabled={!file || busy !== null}>
          {busy === "upload" ? "Importing…" : "Import"}
        </button>
        {result && (
          <div className="result small">
            <p className="positive">
              Added {result.added}, skipped {result.skipped}
            </p>
            {result.errors.length > 0 && (
              <ul>
                {result.errors.map((e) => (
                  <li key={e.row} className="negative">
                    Row {e.row}: {e.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </form>

      <div className="chart-card">
        <h3>Sync holdings from ledger</h3>
        <p className="muted small">
          Rebuilds your Holdings from the ledger's open parcels (FIFO), one row
          per parcel. Replaces any manually-entered holdings for this portfolio.
        </p>
        <button type="button" onClick={sync} disabled={busy !== null}>
          {busy === "sync" ? "Syncing…" : "Sync holdings"}
        </button>
        {message && <p className="positive small">{message}</p>}
      </div>

      {error && <p className="negative small">{error}</p>}
    </div>
  );
}

function LedgerTable({ transactions }: { transactions: Transaction[] }) {
  if (!transactions.length) {
    return <p className="muted">No transactions yet. Import a CSV above.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Ticker</th>
            <th className="num">Qty</th>
            <th className="num">Price</th>
            <th className="num">Value</th>
            <th className="num">Fee</th>
            <th>Ref</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => {
            const ccy = t.currency ?? "AUD";
            return (
              <tr key={t.id}>
                <td>{t.trade_date}</td>
                <td>
                  <span className={t.type === "sell" ? "negative" : "positive"}>
                    {t.type}
                  </span>
                </td>
                <td>
                  <span className="ticker">{t.ticker}</span>
                  <span className="symbol">{t.exchange}</span>
                </td>
                <td className="num">{formatNumber(t.quantity, 4)}</td>
                <td className="num">{formatCurrency(t.price_per_unit, ccy)}</td>
                <td className="num">
                  {formatCurrency(t.quantity * t.price_per_unit, ccy)}
                </td>
                <td className="num">{t.fee ? formatCurrency(t.fee, ccy) : "—"}</td>
                <td className="muted small">{t.reference ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
