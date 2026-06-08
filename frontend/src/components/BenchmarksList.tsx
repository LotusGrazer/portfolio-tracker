import type { Benchmark } from "../api/types";
import { formatPct } from "../utils/format";

interface Props {
  benchmarks: Benchmark[];
}

export function BenchmarksList({ benchmarks }: Props) {
  if (!benchmarks.length) {
    return <p className="muted">No benchmarks defined yet.</p>;
  }
  return (
    <div className="benchmark-grid">
      {benchmarks.map((bench) => (
        <div key={bench.id} className="chart-card">
          <h3>{bench.name}</h3>
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
          <div className="muted small">Total weight {formatPct(bench.total_weight_pct)}</div>
        </div>
      ))}
    </div>
  );
}
