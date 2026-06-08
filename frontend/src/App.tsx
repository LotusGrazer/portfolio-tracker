import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { Benchmark, Comparison, Holding, Summary } from "./api/types";
import { AllocationCharts } from "./components/AllocationCharts";
import { BenchmarkComparison } from "./components/BenchmarkComparison";
import { BenchmarksList } from "./components/BenchmarksList";
import { HoldingsTable } from "./components/HoldingsTable";
import { ManagePanel } from "./components/ManagePanel";
import { SummaryCards } from "./components/SummaryCards";

type Tab = "overview" | "holdings" | "benchmarks" | "compare" | "manage";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "holdings", label: "Holdings" },
  { id: "benchmarks", label: "Benchmarks" },
  { id: "compare", label: "Compare" },
  { id: "manage", label: "Manage" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cmpLoading, setCmpLoading] = useState(false);
  const [cmpError, setCmpError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const loadCore = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, h, b] = await Promise.all([
        api.summary(),
        api.holdings(),
        api.benchmarks(),
      ]);
      setSummary(s);
      setHoldings(h);
      setBenchmarks(b);
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadComparison = useCallback(async () => {
    setCmpLoading(true);
    setCmpError(null);
    try {
      setComparison(await api.compare());
    } catch (e) {
      setCmpError(e instanceof Error ? e.message : String(e));
    } finally {
      setCmpLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCore();
  }, [loadCore]);

  // Lazy-load the (slower) comparison the first time the tab is opened.
  useEffect(() => {
    if (tab === "compare" && comparison === null && !cmpLoading && cmpError === null) {
      loadComparison();
    }
  }, [tab, comparison, cmpLoading, cmpError, loadComparison]);

  const handleChanged = useCallback(() => {
    loadCore();
    setComparison(null); // invalidate; reloads when Compare is next viewed
    setCmpError(null);
  }, [loadCore]);

  const refresh = () => {
    loadCore();
    if (comparison || tab === "compare") loadComparison();
  };

  const baseCurrency = summary?.base_currency ?? "AUD";

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Portfolio Tracker</h1>
          <p className="muted small">
            Base currency {baseCurrency}
            {updatedAt && ` · updated ${updatedAt.toLocaleTimeString("en-AU")}`}
          </p>
        </div>
        <button className="ghost" onClick={refresh} disabled={loading}>
          {loading ? "Refreshing…" : "↻ Refresh"}
        </button>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={t.id === tab ? "tab active" : "tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        {error && !summary ? (
          <div className="chart-card error">
            <h3>Couldn't load data</h3>
            <p className="negative">{error}</p>
            <p className="muted small">
              Start the backend with <code>python app.py</code> (it serves on
              http://localhost:5000), then Refresh.
            </p>
          </div>
        ) : loading && !summary ? (
          <p className="muted">Loading…</p>
        ) : (
          <>
            {tab === "overview" && summary && (
              <>
                <SummaryCards summary={summary} />
                <AllocationCharts summary={summary} />
              </>
            )}
            {tab === "holdings" && (
              <HoldingsTable holdings={holdings} baseCurrency={baseCurrency} />
            )}
            {tab === "benchmarks" && <BenchmarksList benchmarks={benchmarks} />}
            {tab === "compare" && (
              <>
                {cmpLoading && <p className="muted">Computing returns…</p>}
                {cmpError && <p className="negative">{cmpError}</p>}
                {comparison && <BenchmarkComparison comparison={comparison} />}
              </>
            )}
            {tab === "manage" && <ManagePanel onChanged={handleChanged} />}
          </>
        )}
      </main>
    </div>
  );
}
