import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Realised } from "../api/types";
import {
  currentFinancialYear,
  formatCurrency,
  formatPct,
  gainClass,
  recentFinancialYears,
} from "../utils/format";

const ALL = "all";

export function CgtPanel() {
  const [fy, setFy] = useState<string>(currentFinancialYear());
  const [income, setIncome] = useState<string>("");
  const [data, setData] = useState<Realised | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const incomeNum = income.trim() ? Number(income) : undefined;
      const result = await api.realised(fy === ALL ? undefined : fy, incomeNum);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [fy, income]);

  // Reload when the financial year changes (income is applied via the button).
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fy]);

  const cgt = data?.cgt_estimate;
  const ccy = data?.base_currency ?? "AUD";

  return (
    <div>
      <div className="cgt-controls">
        <label className="field inline">
          <span>Financial year</span>
          <select value={fy} onChange={(e) => setFy(e.target.value)}>
            <option value={ALL}>All time</option>
            {recentFinancialYears(6).map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <label className="field inline">
          <span>Taxable income (excl. gains, optional)</span>
          <input
            type="number"
            step="any"
            placeholder="e.g. 120000"
            value={income}
            onChange={(e) => setIncome(e.target.value)}
          />
        </label>
        <button type="button" onClick={load} disabled={loading}>
          {loading ? "Calculating…" : "Calculate"}
        </button>
      </div>

      {error && <p className="negative">{error}</p>}

      {data && data.warnings.length > 0 && (
        <div className="disclaimer" style={{ marginBottom: "1rem" }}>
          {data.warnings.map((w, i) => (
            <div key={i} className="negative small">
              ⚠️ {w}
            </div>
          ))}
        </div>
      )}

      {cgt && (
        <>
          <div className="cards">
            <Card label="Total realised gain" value={formatCurrency(cgt.total_realised_gain, ccy)} tone={gainClass(cgt.total_realised_gain)} />
            <Card label="Held > 12mo (eligible)" value={formatCurrency(cgt.discount_eligible_gain, ccy)} sub="Qualifies for 50% discount" />
            <Card label="50% discount" value={`− ${formatCurrency(cgt.estimated_discount, ccy)}`} />
            <Card label="Net capital gain" value={formatCurrency(cgt.estimated_net_capital_gain, ccy)} tone={gainClass(cgt.estimated_net_capital_gain)} />
            {cgt.estimated_tax && (
              <Card
                label="Est. tax on gain"
                value={formatCurrency(cgt.estimated_tax.additional_tax, ccy)}
                sub={`${formatPct(cgt.estimated_tax.effective_rate_on_gain_pct)} effective · FY ${cgt.estimated_tax.financial_year_basis}`}
                tone="negative"
              />
            )}
          </div>

          {!cgt.estimated_tax && (
            <p className="muted small">
              Enter your taxable income above and Calculate to estimate the tax
              this gain would attract.
            </p>
          )}

          <RealisedTable data={data!} />

          <p className="muted small disclaimer">⚠️ {cgt.disclaimer} Not tax advice.</p>
        </>
      )}
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
      {sub && <div className="card-sub muted">{sub}</div>}
    </div>
  );
}

function RealisedTable({ data }: { data: Realised }) {
  if (!data.events.length) {
    return <p className="muted">No sells in this period.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th className="num">Qty</th>
            <th>Acquired</th>
            <th>Sold</th>
            <th className="num">Proceeds</th>
            <th className="num">Cost base</th>
            <th className="num">Gain</th>
            <th>CGT discount</th>
          </tr>
        </thead>
        <tbody>
          {data.events.map((e, i) => {
            const ccy = e.currency ?? data.base_currency;
            return (
              <tr key={i}>
                <td className="ticker">{e.ticker}</td>
                <td className="num">{e.quantity}</td>
                <td>{e.buy_date}</td>
                <td>{e.sell_date}</td>
                <td className="num">{formatCurrency(e.proceeds, ccy)}</td>
                <td className="num">{formatCurrency(e.cost_base, ccy)}</td>
                <td className={`num ${gainClass(e.gain)}`}>
                  {formatCurrency(e.gain, ccy)}
                </td>
                <td>
                  {e.cgt_discount_eligible ? (
                    <span className="positive small">eligible</span>
                  ) : (
                    <span className="muted small">&lt; 12mo</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
