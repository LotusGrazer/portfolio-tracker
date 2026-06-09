import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { Benchmark, Holding, Summary, Transaction } from "./api/types";
import { AllocationCharts } from "./components/AllocationCharts";
import { BenchmarksList } from "./components/BenchmarksList";
import { CgtPanel } from "./components/CgtPanel";
import { ComparePanel } from "./components/ComparePanel";
import { HoldingsView } from "./components/HoldingsView";
import { Loading } from "./components/Loading";
import { ManagePanel } from "./components/ManagePanel";
import { SummaryCards } from "./components/SummaryCards";
import { TransactionsPanel } from "./components/TransactionsPanel";

type Tab =
  | "overview"
  | "holdings"
  | "benchmarks"
  | "compare"
  | "transactions"
  | "cgt"
  | "manage";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "holdings", label: "Holdings" },
  { id: "benchmarks", label: "Benchmarks" },
  { id: "compare", label: "Compare" },
  { id: "transactions", label: "Transactions" },
  { id: "cgt", label: "CGT" },
  { id: "manage", label: "Manage" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const loadCore = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, h, b, t] = await Promise.all([
        api.summary(),
        api.holdings(),
        api.benchmarks(),
        api.transactions(),
      ]);
      setSummary(s);
      setHoldings(h);
      setBenchmarks(b);
      setTransactions(t);
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCore();
  }, [loadCore]);

  const handleChanged = useCallback(() => {
    loadCore();
  }, [loadCore]);

  const refresh = () => loadCore();

  const baseCurrency = summary?.base_currency ?? "AUD";

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Portfolio Tracker</h1>
          <p className="muted small">
            Base currency {baseCurrency}
            {loading ? (
              <span className="updating">
                {" · "}
                <span className="spinner" /> updating prices…
              </span>
            ) : (
              updatedAt && ` · updated ${updatedAt.toLocaleTimeString("en-AU")}`
            )}
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
          <Loading
            message="Fetching live prices…"
            hint="The first load after starting fetches a current price for every ticker — this can take a few seconds. It's cached after that."
          />
        ) : (
          <>
            {tab === "overview" && summary && (
              <>
                <SummaryCards summary={summary} />
                <AllocationCharts summary={summary} />
              </>
            )}
            {tab === "holdings" && (
              <HoldingsView holdings={holdings} baseCurrency={baseCurrency} />
            )}
            {tab === "benchmarks" && (
              <BenchmarksList benchmarks={benchmarks} onChanged={handleChanged} />
            )}
            {tab === "transactions" && (
              <TransactionsPanel
                transactions={transactions}
                onChanged={handleChanged}
              />
            )}
            {tab === "cgt" && <CgtPanel />}
            {tab === "compare" && <ComparePanel />}
            {tab === "manage" && <ManagePanel onChanged={handleChanged} />}
          </>
        )}
      </main>
    </div>
  );
}
