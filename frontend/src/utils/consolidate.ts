import type { Holding } from "../api/types";

// A position aggregated across all its FIFO parcels (one row per ticker).
export interface ConsolidatedHolding {
  ticker: string;
  symbol: string;
  exchange: string | null;
  quantity: number;
  avgCostPerUnitBase: number | null; // weighted average, in base currency
  currentPrice: number | null;
  priceCurrency: string | null;
  marketValueBase: number | null;
  costBaseTotalBase: number | null;
  gainLossBase: number | null;
  gainLossPct: number | null;
  parcels: number;
}

/**
 * Group per-parcel holdings into one row per ticker, summing quantities and
 * values and computing a weighted-average cost. Sorted by market value desc.
 * Unpriced parcels contribute their quantity but not value (so a partially
 * priced position still shows what's known).
 */
export function consolidateHoldings(holdings: Holding[]): ConsolidatedHolding[] {
  const groups = new Map<string, ConsolidatedHolding>();

  for (const h of holdings) {
    const key = `${h.ticker}|${h.exchange ?? ""}`;
    let g = groups.get(key);
    if (!g) {
      g = {
        ticker: h.ticker,
        symbol: h.symbol,
        exchange: h.exchange,
        quantity: 0,
        avgCostPerUnitBase: null,
        currentPrice: h.current_price,
        priceCurrency: h.price_currency,
        marketValueBase: null,
        costBaseTotalBase: null,
        gainLossBase: null,
        gainLossPct: null,
        parcels: 0,
      };
      groups.set(key, g);
    }
    g.quantity += h.quantity ?? 0;
    g.parcels += 1;
    if (h.market_value_base != null) {
      g.marketValueBase = (g.marketValueBase ?? 0) + h.market_value_base;
    }
    if (h.cost_base_total_base != null) {
      g.costBaseTotalBase = (g.costBaseTotalBase ?? 0) + h.cost_base_total_base;
    }
    if (g.currentPrice == null && h.current_price != null) {
      g.currentPrice = h.current_price;
    }
    if (g.priceCurrency == null && h.price_currency != null) {
      g.priceCurrency = h.price_currency;
    }
  }

  const result = [...groups.values()];
  for (const g of result) {
    if (g.costBaseTotalBase != null && g.quantity) {
      g.avgCostPerUnitBase = g.costBaseTotalBase / g.quantity;
    }
    if (g.marketValueBase != null && g.costBaseTotalBase != null) {
      g.gainLossBase = g.marketValueBase - g.costBaseTotalBase;
      g.gainLossPct = g.costBaseTotalBase
        ? (g.gainLossBase / g.costBaseTotalBase) * 100
        : null;
    }
  }
  result.sort((a, b) => (b.marketValueBase ?? 0) - (a.marketValueBase ?? 0));
  return result;
}
