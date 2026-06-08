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
  const [portfolio, setPortfolio] = useState("My Portfolio");
  const [replace, setReplace] = useState(true);
  const [rebuild, setRebuild] = useState(true);
  const [busy, setBusy] = useState<"import" | "sync" | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function importTxns(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const name = portfolio.trim() || undefined;
    setBusy("import");
    setError(null);
    setResult(null);
    setMessage(null);
    try {
      const res = await api.uploadTransactions(file, name, replace);
      setResult(res);
      if (rebuild) {
        const synced = await api.syncHoldings(name);
        const warn = synced.warnings.length
          ? ` (${synced.warnings.length} skipped: ${synced.warnings.join("; ")})`
          : "";
        setMessage(`Built ${synced.holdings_created} holding parcel(s).${warn}`);
      }
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
      const res = await api.syncHoldings(portfolio.trim() || undefined);
      const warn = res.warnings.length
        ? ` ${res.warnings.length} ticker(s) skipped: ${res.warnings.join("; ")}`
        : "";
      setMessage(
        `Rebuilt ${res.holdings_created} holding parcel(s) from ${res.tickers.length} ticker(s).${warn}`,
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
      <form className="chart-card" onSubmit={importTxns}>
        <h3>Import transactions (CSV)</h3>
        <p className="muted small">
          Upload a <strong>CMC Cash Transaction Summary</strong> export directly
          (auto-detected — trades are parsed; deposits/dividends/interest are
          skipped). Or a native CSV: ticker, type (buy/sell), quantity,
          price_per_unit, trade_date (+ optional exchange, fee, reference,
          currency).
        </p>
        <label className="field">
          <span>CSV file</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label className="field">
          <span>Portfolio name</span>
          <input value={portfolio} onChange={(e) => setPortfolio(e.target.value)} />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={replace}
            onChange={(e) => setReplace(e.target.checked)}
          />
          <span>Replace existing transactions in this portfolio</span>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={rebuild}
            onChange={(e) => setRebuild(e.target.checked)}
          />
          <span>Build holdings from these transactions (recommended)</span>
        </label>
        <button type="submit" disabled={!file || busy !== null}>
          {busy === "import" ? "Importing…" : "Import"}
        </button>
        {result && (
          <div className="result small">
            <p className="positive">
              Added {result.added} trade(s), skipped {result.skipped} non-trade
              row(s) → {result.portfolio}
            </p>
            {message && <p className="positive">{message}</p>}
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
        <h3>Rebuild holdings from ledger</h3>
        <p className="muted small">
          Rebuilds the named portfolio's Holdings from its open parcels (FIFO),
          one row per parcel. Useful after manually editing transactions.
          Replaces any manually-entered holdings for that portfolio.
        </p>
        <button type="button" onClick={sync} disabled={busy !== null}>
          {busy === "sync" ? "Rebuilding…" : "Rebuild holdings"}
        </button>
        {!result && message && <p className="positive small">{message}</p>}
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
