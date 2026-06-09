import { useState } from "react";
import { api } from "../api/client";
import type { Benchmark } from "../api/types";
import { formatPct } from "../utils/format";

interface Props {
  benchmarks: Benchmark[];
  onChanged: () => void;
}

export function BenchmarksList({ benchmarks, onChanged }: Props) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove(bench: Benchmark) {
    if (!window.confirm(`Delete benchmark "${bench.name}"?`)) return;
    setBusyId(bench.id);
    setError(null);
    try {
      await api.deleteBenchmark(bench.id);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  if (!benchmarks.length) {
    return <p className="muted">No benchmarks defined yet. Add one in the Manage tab.</p>;
  }
  return (
    <>
      {error && <p className="negative small">{error}</p>}
      <div className="benchmark-grid">
        {benchmarks.map((bench) => {
          const offTarget = Math.abs(bench.total_weight_pct - 100) > 0.01;
          return (
            <div key={bench.id} className="chart-card">
              <div className="card-head">
                <h3>{bench.name}</h3>
                <button
                  type="button"
                  className="ghost danger"
                  onClick={() => remove(bench)}
                  disabled={busyId === bench.id}
                  title="Delete benchmark"
                >
                  {busyId === bench.id ? "…" : "Delete"}
                </button>
              </div>
              {bench.warning && <p className="negative small">{bench.warning}</p>}
              <ul className="constituents">
                {bench.constituents.map((c) => (
                  <li key={`${c.ticker}-${c.exchange}`}>
                    <span className="legend-key">
                      {c.ticker}
                      {c.exchange ? <span className="symbol"> {c.exchange}</span> : null}
                    </span>
                    <span className="legend-val">{formatPct(c.weight_pct)}</span>
                  </li>
                ))}
              </ul>
              <div className={`muted small ${offTarget ? "negative" : ""}`}>
                Total weight {formatPct(bench.total_weight_pct)}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
