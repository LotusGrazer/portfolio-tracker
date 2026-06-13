import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { Performance } from "../api/types";
import { formatCurrency, formatNumber, formatPct, gainClass } from "../utils/format";
import { Loading } from "./Loading";

const PALETTE = ["#4f7cff", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];
const ACTUAL_COLOR = "#0f172a";

const PERIODS: [string, string][] = [
  ["3mo", "3M"],
  ["6mo", "6M"],
  ["ytd", "YTD"],
  ["1y", "1Y"],
  ["3y", "3Y"],
  ["5y", "5Y"],
  ["max", "All"],
];

export function PerformancePanel() {
  const [period, setPeriod] = useState("max");
  const [data, setData] = useState<Performance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.performance(period));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <p className="negative">{error}</p>;
  if (loading && !data) {
    return (
      <Loading
        message="Reconstructing performance…"
        hint="Building your portfolio's daily value from the transaction ledger and full price history."
      />
    );
  }
  if (!data) return null;

  if (!data.available) {
    return (
      <div className="chart-card">
        <h3>Actual performance</h3>
        <p className="muted">{data.reason}</p>
      </div>
    );
  }

  const ccy = data.base_currency ?? "AUD";
  const benchmarks = data.benchmarks ?? [];
  const series = data.series ?? [];

  return (
    <div>
      <div className="toggle-row">
        {PERIODS.map(([k, label]) => (
          <button
            key={k}
            className={period === k ? "pill active" : "pill"}
            onClick={() => setPeriod(k)}
          >
            {label}
          </button>
        ))}
        {loading && <span className="muted small"> updating…</span>}
      </div>

      <div className="cards">
        <Card
          label="Time-weighted return"
          value={formatPct(data.twr_pct, true)}
          sub={
            data.twr_annualised_pct != null
              ? `${formatPct(data.twr_annualised_pct, true)} p.a.`
              : undefined
          }
          tone={gainClass(data.twr_pct)}
        />
        <Card
          label="Money-weighted (XIRR)"
          value={
            data.money_weighted_pct != null
              ? `${formatPct(data.money_weighted_pct, true)} p.a.`
              : "—"
          }
          sub="What your actual dollars earned"
          tone={gainClass(data.money_weighted_pct)}
        />
        <Card
          label="Current value"
          value={formatCurrency(data.current_value, ccy)}
          sub={`Net invested ${formatCurrency(data.net_invested, ccy)} this period`}
        />
        <Card
          label="Income received"
          value={formatCurrency(data.income_received, ccy)}
          sub="Dividends / distributions (ex-date)"
        />
      </div>

      <div className="chart-card wide">
        <h3>
          Growth of 100 — actual portfolio vs benchmarks ({ccy},{" "}
          {data.start_date} → {data.end_date})
        </h3>
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" minTickGap={48} />
            <YAxis domain={["auto", "auto"]} />
            <Tooltip />
            <Legend />
            <Line
              type="monotone"
              dataKey="portfolio"
              name="Actual portfolio"
              stroke={ACTUAL_COLOR}
              strokeWidth={2}
              dot={false}
            />
            {benchmarks.map((bench, i) => (
              <Line
                key={bench.id}
                type="monotone"
                dataKey={bench.name}
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={1.5}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {benchmarks.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Series</th>
                <th className="num">Return</th>
                <th className="num">p.a.</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>Actual portfolio</strong>
                </td>
                <td className={`num ${gainClass(data.twr_pct)}`}>
                  {formatPct(data.twr_pct, true)}
                </td>
                <td className={`num ${gainClass(data.twr_annualised_pct)}`}>
                  {formatPct(data.twr_annualised_pct, true)}
                </td>
              </tr>
              {benchmarks.map((bench) => (
                <tr key={bench.id}>
                  <td>{bench.name}</td>
                  <td className="num">{formatPct(bench.return_pct, true)}</td>
                  <td className="num">
                    {formatPct(bench.annualised_return_pct, true)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.metrics && data.metrics.observations >= 20 && (
        <MetricsTable metrics={data.metrics} />
      )}

      {(data.warnings ?? []).map((w) => (
        <p key={w} className="muted small">
          ⚠ {w}
        </p>
      ))}
      <p className="muted small">
        Unlike the Compare tab (which asks how your <em>current</em> allocation
        would have performed), this reconstructs what you actually held each day
        from the transaction ledger. The time-weighted return strips out the
        timing of your contributions, making it comparable to the benchmarks;
        the money-weighted return includes that timing — it's the rate your
        invested dollars actually earned. Dividends are counted as cash income
        on their ex-dates (not auto-reinvested), while benchmarks assume
        reinvestment — any cash drag is real and shows here.
      </p>
    </div>
  );
}

function MetricsTable({ metrics }: { metrics: NonNullable<Performance["metrics"]> }) {
  const m = metrics;
  // pct: percentage metric; otherwise a plain ratio. portfolio=null marks a
  // relational metric (portfolio vs each benchmark) with no standalone value.
  const rows: {
    label: string;
    pct?: boolean;
    portfolio: number | null;
    pick: (b: (typeof m.benchmarks)[number]) => number | null;
  }[] = [
    {
      label: "Annualised volatility",
      pct: true,
      portfolio: m.portfolio.annualised_volatility_pct,
      pick: (b) => b.annualised_volatility_pct,
    },
    {
      label: "Max drawdown",
      pct: true,
      portfolio: m.portfolio.max_drawdown_pct,
      pick: (b) => b.max_drawdown_pct,
    },
    {
      label: "Sharpe ratio",
      portfolio: m.portfolio.sharpe_ratio,
      pick: (b) => b.sharpe_ratio,
    },
    { label: "Beta", portfolio: null, pick: (b) => b.beta },
    { label: "Correlation", portfolio: null, pick: (b) => b.correlation },
    {
      label: "Tracking error",
      pct: true,
      portfolio: null,
      pick: (b) => b.tracking_error_pct,
    },
    {
      label: "Information ratio",
      portfolio: null,
      pick: (b) => b.information_ratio,
    },
    { label: "Alpha (p.a.)", pct: true, portfolio: null, pick: (b) => b.alpha_pct },
  ];
  const fmt = (v: number | null, pct?: boolean) =>
    pct ? formatPct(v, true) : formatNumber(v, 2);

  return (
    <div className="table-wrap">
      <h3>Risk &amp; risk-adjusted metrics</h3>
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            <th className="num">Portfolio</th>
            {m.benchmarks.map((b) => (
              <th key={b.id} className="num">
                {b.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <td>{row.label}</td>
              <td className="num">{fmt(row.portfolio, row.pct)}</td>
              {m.benchmarks.map((b) => (
                <td key={b.id} className="num">
                  {fmt(row.pick(b), row.pct)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Computed from daily returns ({m.observations} trading days,{" "}
        {m.trading_days_basis}-day annualisation). Beta, correlation, tracking
        error, information ratio and alpha describe the <strong>portfolio
        relative to that benchmark</strong>. Sharpe and alpha assume a{" "}
        {formatPct(m.risk_free_rate_pct)} risk-free rate (set{" "}
        <code>RISK_FREE_RATE</code> to change).
        {!m.annualised_ratios &&
          " Sharpe, information ratio and alpha need a year-plus window and are hidden for shorter periods."}{" "}
        Periods holding tickers without price history have understated
        volatility (their values are interpolated).
      </p>
    </div>
  );
}

function Card({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="card">
      <div className="card-label">{label}</div>
      <div className={`card-value ${tone}`}>{value}</div>
      {sub && <div className={`card-sub ${tone}`}>{sub}</div>}
    </div>
  );
}
