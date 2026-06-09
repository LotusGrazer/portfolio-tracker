import { useState } from "react";
import type { Holding } from "../api/types";
import { consolidateHoldings } from "../utils/consolidate";
import {
  formatCurrency,
  formatNumber,
  formatPct,
  gainClass,
} from "../utils/format";
import { HoldingsTable } from "./HoldingsTable";

interface Props {
  holdings: Holding[];
  baseCurrency: string;
}

export function HoldingsView({ holdings, baseCurrency }: Props) {
  const [view, setView] = useState<"consolidated" | "parcels">("consolidated");

  if (!holdings.length) {
    return (
      <p className="muted">
        No holdings yet. Import transactions (Transactions tab) or upload a
        holdings CSV (Manage tab).
      </p>
    );
  }

  return (
    <div>
      <div className="toggle-row">
        <button
          className={view === "consolidated" ? "pill active" : "pill"}
          onClick={() => setView("consolidated")}
        >
          Consolidated
        </button>
        <button
          className={view === "parcels" ? "pill active" : "pill"}
          onClick={() => setView("parcels")}
        >
          Parcels ({holdings.length})
        </button>
      </div>

      {view === "consolidated" ? (
        <ConsolidatedTable holdings={holdings} baseCurrency={baseCurrency} />
      ) : (
        <HoldingsTable holdings={holdings} baseCurrency={baseCurrency} />
      )}
    </div>
  );
}

function ConsolidatedTable({ holdings, baseCurrency }: Props) {
  const rows = consolidateHoldings(holdings);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Exch.</th>
            <th className="num">Qty</th>
            <th className="num">Avg cost</th>
            <th className="num">Price</th>
            <th className="num">Market value</th>
            <th className="num">Cost base</th>
            <th className="num">Gain / loss</th>
            <th className="num">%</th>
            <th className="num">Parcels</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.ticker}-${r.exchange}`}>
              <td>
                <span className="ticker">{r.ticker}</span>
                <span className="symbol">{r.symbol}</span>
              </td>
              <td>{r.exchange ?? "—"}</td>
              <td className="num">{formatNumber(r.quantity, 4)}</td>
              <td className="num">{formatCurrency(r.avgCostPerUnitBase, baseCurrency)}</td>
              <td className="num">
                {formatCurrency(r.currentPrice, r.priceCurrency ?? baseCurrency)}
              </td>
              <td className="num">{formatCurrency(r.marketValueBase, baseCurrency)}</td>
              <td className="num">{formatCurrency(r.costBaseTotalBase, baseCurrency)}</td>
              <td className={`num ${gainClass(r.gainLossBase)}`}>
                {formatCurrency(r.gainLossBase, baseCurrency)}
              </td>
              <td className={`num ${gainClass(r.gainLossPct)}`}>
                {formatPct(r.gainLossPct, true)}
              </td>
              <td className="num muted">{r.parcels}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
