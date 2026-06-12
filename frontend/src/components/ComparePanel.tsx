import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Comparison } from "../api/types";
import { BenchmarkComparison } from "./BenchmarkComparison";
import { Loading } from "./Loading";

// Ordered list of selectable periods (chronological for the chart x-axis).
const PERIODS: [string, string][] = [
  ["1mo", "1M"],
  ["3mo", "3M"],
  ["6mo", "6M"],
  ["ytd", "YTD"],
  ["1y", "1Y"],
  ["2y", "2Y"],
  ["3y", "3Y"],
  ["5y", "5Y"],
  ["10y", "10Y"],
  ["max", "All"],
];
const DEFAULT_SELECTED = ["3mo", "1y", "5y", "max"];

export function ComparePanel() {
  const [selected, setSelected] = useState<string[]>(DEFAULT_SELECTED);
  const [data, setData] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ordered = PERIODS.map(([k]) => k).filter((k) => selected.includes(k));
  const key = ordered.join(",");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.compare(key ? key.split(",") : undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    load();
  }, [load]);

  function toggle(p: string) {
    setSelected((s) =>
      s.includes(p) ? (s.length > 1 ? s.filter((x) => x !== p) : s) : [...s, p],
    );
  }

  return (
    <div>
      <div className="toggle-row">
        {PERIODS.map(([k, label]) => (
          <button
            key={k}
            className={selected.includes(k) ? "pill active" : "pill"}
            onClick={() => toggle(k)}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="negative">{error}</p>}
      {loading && !data ? (
        <Loading message="Computing returns…" hint="Fetching price history for each holding and benchmark." />
      ) : data ? (
        <BenchmarkComparison comparison={data} />
      ) : null}

      <p className="muted small">
        "All" uses each security's full history — benchmarks of funds with
        different inception dates are measured over different windows. Each
        security is annualised over its own span, which puts them on the same
        scale, but the windows still cover different market periods.
      </p>
    </div>
  );
}
