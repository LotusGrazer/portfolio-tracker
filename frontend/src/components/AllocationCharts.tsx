import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { Breakdown, Summary } from "../api/types";
import { formatCurrency, formatPct } from "../utils/format";

const PALETTE = [
  "#4f7cff",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#ec4899",
  "#84cc16",
];

interface Props {
  summary: Summary;
}

export function AllocationCharts({ summary }: Props) {
  return (
    <div className="charts">
      <Donut title="By asset class" data={summary.by_asset_class} currency={summary.base_currency} />
      <Donut title="By currency" data={summary.by_currency} currency={summary.base_currency} />
      <Donut title="By broker" data={summary.by_broker} currency={summary.base_currency} />
    </div>
  );
}

function Donut({
  title,
  data,
  currency,
}: {
  title: string;
  data: Breakdown[];
  currency: string;
}) {
  if (!data.length) {
    return (
      <div className="chart-card">
        <h3>{title}</h3>
        <p className="muted">No data yet.</p>
      </div>
    );
  }
  return (
    <div className="chart-card">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="key"
            innerRadius={55}
            outerRadius={85}
            paddingAngle={2}
          >
            {data.map((entry, i) => (
              <Cell key={entry.key} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, _name, item) => [
              `${formatCurrency(Number(value), currency)} (${formatPct(
                (item?.payload as Breakdown)?.weight_pct,
              )})`,
              (item?.payload as Breakdown)?.key,
            ]}
          />
        </PieChart>
      </ResponsiveContainer>
      <ul className="legend">
        {data.map((entry, i) => (
          <li key={entry.key}>
            <span
              className="swatch"
              style={{ background: PALETTE[i % PALETTE.length] }}
            />
            <span className="legend-key">{entry.key}</span>
            <span className="legend-val">{formatPct(entry.weight_pct)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
