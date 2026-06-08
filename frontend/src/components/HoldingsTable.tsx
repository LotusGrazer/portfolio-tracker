import type { Holding } from "../api/types";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPct,
  gainClass,
} from "../utils/format";

interface Props {
  holdings: Holding[];
  baseCurrency: string;
}

export function HoldingsTable({ holdings, baseCurrency }: Props) {
  if (!holdings.length) {
    return <p className="muted">No holdings yet. Upload a CSV in the Manage tab.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Exch.</th>
            <th className="num">Qty</th>
            <th className="num">Price</th>
            <th className="num">Market value</th>
            <th className="num">Cost base</th>
            <th className="num">Gain / loss</th>
            <th className="num">%</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => (
            <tr key={h.id}>
              <td>
                <span className="ticker">{h.ticker}</span>
                <span className="symbol">{h.symbol}</span>
              </td>
              <td>{h.exchange ?? "—"}</td>
              <td className="num">{formatNumber(h.quantity, 4)}</td>
              <td className="num">
                {formatCurrency(h.current_price, h.price_currency ?? baseCurrency)}
              </td>
              <td className="num">{formatCurrency(h.market_value_base, baseCurrency)}</td>
              <td className="num">{formatCurrency(h.cost_base_total_base, baseCurrency)}</td>
              <td className={`num ${gainClass(h.gain_loss_base)}`}>
                {formatCurrency(h.gain_loss_base, baseCurrency)}
              </td>
              <td className={`num ${gainClass(h.gain_loss_pct)}`}>
                {formatPct(h.gain_loss_pct, true)}
              </td>
              <td className="muted small">{formatDateTime(h.price_last_updated)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
