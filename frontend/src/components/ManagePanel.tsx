import { useState } from "react";
import { api } from "../api/client";
import type { UploadResult } from "../api/types";

const EXCHANGES = ["ASX", "US", "CBOE_AU", "CRYPTO", "RAW"];

interface Props {
  onChanged: () => void;
}

export function ManagePanel({ onChanged }: Props) {
  return (
    <div className="manage-grid">
      <HoldingsUpload onChanged={onChanged} />
      <BenchmarkBuilder onChanged={onChanged} />
    </div>
  );
}

function HoldingsUpload({ onChanged }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [portfolio, setPortfolio] = useState("My Portfolio");
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.uploadHoldings(file, portfolio || undefined, replace);
      setResult(res);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="chart-card" onSubmit={submit}>
      <h3>Upload holdings (CSV)</h3>
      <p className="muted small">
        A point-in-time snapshot. Columns: ticker, quantity, cost_base_per_unit,
        date_acquired, broker, asset_class, exchange, cost_currency.{" "}
        <em>Importing a CMC export? Use the Transactions tab instead.</em>
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
        <span>Replace existing holdings in this portfolio</span>
      </label>
      <button type="submit" disabled={!file || busy}>
        {busy ? "Uploading…" : "Upload"}
      </button>

      {error && <p className="negative small">{error}</p>}
      {result && (
        <div className="result small">
          <p className="positive">
            Added {result.added}, skipped {result.skipped} → {result.portfolio}
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
  );
}

interface Row {
  ticker: string;
  weight_pct: string;
  exchange: string;
}

function BenchmarkBuilder({ onChanged }: Props) {
  const [name, setName] = useState("");
  const [rows, setRows] = useState<Row[]>([{ ticker: "", weight_pct: "", exchange: "ASX" }]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const totalWeight = rows.reduce((sum, r) => sum + (parseFloat(r.weight_pct) || 0), 0);

  function updateRow(i: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((rs) => [...rs, { ticker: "", weight_pct: "", exchange: "ASX" }]);
  }
  function removeRow(i: number) {
    setRows((rs) => (rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const constituents = rows
        .filter((r) => r.ticker.trim())
        .map((r) => ({
          ticker: r.ticker.trim().toUpperCase(),
          weight_pct: parseFloat(r.weight_pct) || 0,
          exchange: r.exchange,
        }));
      const created = await api.createBenchmark({ name: name.trim(), constituents });
      setMessage(
        `Saved "${created.name}"${created.warning ? ` (${created.warning})` : ""}`,
      );
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="chart-card" onSubmit={submit}>
      <h3>Create benchmark</h3>
      <p className="muted small">
        Rows are weighted constituents, e.g. 50% IQLT + 25% IVLU + 25% IMTM on
        CBOE_AU. Saving a name that exists replaces it.
      </p>
      <label className="field">
        <span>Name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="MSCI World"
          required
        />
      </label>

      <div className="constituent-rows">
        {rows.map((row, i) => (
          <div className="constituent-row" key={i}>
            <input
              placeholder="Ticker"
              value={row.ticker}
              onChange={(e) => updateRow(i, { ticker: e.target.value })}
            />
            <input
              placeholder="Weight %"
              type="number"
              step="any"
              value={row.weight_pct}
              onChange={(e) => updateRow(i, { weight_pct: e.target.value })}
            />
            <select
              value={row.exchange}
              onChange={(e) => updateRow(i, { exchange: e.target.value })}
            >
              {EXCHANGES.map((ex) => (
                <option key={ex} value={ex}>
                  {ex}
                </option>
              ))}
            </select>
            <button type="button" className="ghost" onClick={() => removeRow(i)}>
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="row-actions">
        <button type="button" className="ghost" onClick={addRow}>
          + Add constituent
        </button>
        <span className={`small ${Math.abs(totalWeight - 100) < 0.01 ? "positive" : "muted"}`}>
          Total {totalWeight.toFixed(2)}%
        </span>
      </div>

      <button type="submit" disabled={busy || !name.trim()}>
        {busy ? "Saving…" : "Save benchmark"}
      </button>

      {error && <p className="negative small">{error}</p>}
      {message && <p className="positive small">{message}</p>}
    </form>
  );
}
