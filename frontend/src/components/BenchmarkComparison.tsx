import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Comparison } from "../api/types";
import { formatPct, gainClass } from "../utils/format";

const PALETTE = ["#4f7cff", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];
const ACTUAL_COLOR = "#0f172a";

interface Props {
  comparison: Comparison;
}

export function BenchmarkComparison({ comparison }: Props) {
  const { periods, actual, benchmarks } = comparison;

  if (!benchmarks.length) {
    return (
      <p className="muted">
        No benchmarks yet. Create one in the Manage tab (e.g. MSCI World, ASX 200,
        or a factor blend) to compare against.
      </p>
    );
  }

  const chartData = periods.map((period) => {
    const row: Record<string, number | string | null> = {
      period,
      Actual: actual[period]?.return_pct ?? null,
    };
    for (const bench of benchmarks) {
      row[bench.name] = bench.periods[period]?.benchmark_return_pct ?? null;
    }
    return row;
  });

  return (
    <div>
      <div className="chart-card wide">
        <h3>Return by period ({comparison.base_currency}, FX-adjusted)</h3>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="period" />
            <YAxis unit="%" />
            <Tooltip formatter={(v) => formatPct(Number(v), true)} />
            <Legend />
            <Bar dataKey="Actual" fill={ACTUAL_COLOR} radius={[3, 3, 0, 0]} />
            {benchmarks.map((bench, i) => (
              <Bar
                key={bench.id}
                dataKey={bench.name}
                fill={PALETTE[i % PALETTE.length]}
                radius={[3, 3, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Series</th>
              {periods.map((p) => (
                <th key={p} className="num">
                  {p}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <strong>Actual portfolio</strong>
              </td>
              {periods.map((p) => (
                <td key={p} className={`num ${gainClass(actual[p]?.return_pct)}`}>
                  {formatPct(actual[p]?.return_pct, true)}
                </td>
              ))}
            </tr>
            {benchmarks.map((bench) => (
              <tr key={bench.id}>
                <td>{bench.name}</td>
                {periods.map((p) => {
                  const cell = bench.periods[p];
                  return (
                    <td key={p} className="num">
                      <div>{formatPct(cell?.benchmark_return_pct, true)}</div>
                      <div className={`small ${gainClass(cell?.excess_return_pct)}`}>
                        {formatPct(cell?.excess_return_pct, true)} excess
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Excess = actual − benchmark. Returns are <strong>total return</strong>
        {" "}(dividends reinvested, via each security's accumulation series), so
        use dividend-paying ETFs as benchmarks rather than price-only indices.
      </p>
    </div>
  );
}
