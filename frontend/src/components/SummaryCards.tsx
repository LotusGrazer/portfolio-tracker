import type { Summary } from "../api/types";
import { formatCurrency, formatPct, gainClass } from "../utils/format";

interface Props {
  summary: Summary;
}

export function SummaryCards({ summary }: Props) {
  const ccy = summary.base_currency;
  return (
    <div className="cards">
      <Card label="Total value" value={formatCurrency(summary.total_market_value, ccy)} />
      <Card label="Cost base" value={formatCurrency(summary.total_cost_base, ccy)} />
      <Card
        label="Gain / loss"
        value={formatCurrency(summary.total_gain_loss, ccy)}
        sub={formatPct(summary.total_gain_loss_pct, true)}
        tone={gainClass(summary.total_gain_loss)}
      />
      <Card
        label="Holdings priced"
        value={`${summary.holdings_priced} / ${summary.holdings_count}`}
        sub={
          summary.unpriced_tickers.length
            ? `Unpriced: ${summary.unpriced_tickers.join(", ")}`
            : "All holdings priced"
        }
        tone={summary.unpriced_tickers.length ? "negative" : "neutral"}
      />
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
