import { describe, expect, it } from "vitest";
import type { Holding } from "../api/types";
import { consolidateHoldings } from "./consolidate";

function parcel(over: Partial<Holding>): Holding {
  return {
    id: Math.random(),
    portfolio_id: 1,
    ticker: "X",
    exchange: "ASX",
    quantity: 0,
    cost_base_per_unit: null,
    cost_currency: null,
    date_acquired: null,
    broker: null,
    asset_class: "stock",
    weight_pct: null,
    symbol: "X.AX",
    current_price: 10,
    price_currency: "AUD",
    price_last_updated: null,
    fx_rate_to_base: 1,
    market_value: null,
    market_value_base: null,
    cost_base_total: null,
    cost_base_currency: "AUD",
    cost_base_total_base: null,
    gain_loss_base: null,
    gain_loss_pct: null,
    base_currency: "AUD",
    ...over,
  };
}

describe("consolidateHoldings", () => {
  it("groups parcels of the same ticker and sums quantity/value", () => {
    const rows = consolidateHoldings([
      parcel({ ticker: "CGF", quantity: 100, market_value_base: 900, cost_base_total_base: 600 }),
      parcel({ ticker: "CGF", quantity: 50, market_value_base: 450, cost_base_total_base: 400 }),
      parcel({ ticker: "AOV", quantity: 10, market_value_base: 60, cost_base_total_base: 50 }),
    ]);
    const cgf = rows.find((r) => r.ticker === "CGF")!;
    expect(cgf.parcels).toBe(2);
    expect(cgf.quantity).toBe(150);
    expect(cgf.marketValueBase).toBe(1350);
    expect(cgf.costBaseTotalBase).toBe(1000);
    expect(cgf.gainLossBase).toBe(350);
    expect(cgf.avgCostPerUnitBase).toBeCloseTo(1000 / 150);
    expect(cgf.gainLossPct).toBeCloseTo(35);
  });

  it("sorts by market value descending", () => {
    const rows = consolidateHoldings([
      parcel({ ticker: "SMALL", quantity: 1, market_value_base: 10, cost_base_total_base: 10 }),
      parcel({ ticker: "BIG", quantity: 1, market_value_base: 1000, cost_base_total_base: 1 }),
    ]);
    expect(rows.map((r) => r.ticker)).toEqual(["BIG", "SMALL"]);
  });

  it("includes unpriced quantity but leaves value null", () => {
    const rows = consolidateHoldings([
      parcel({ ticker: "DEAD", quantity: 5, current_price: null, market_value_base: null }),
    ]);
    expect(rows[0].quantity).toBe(5);
    expect(rows[0].marketValueBase).toBeNull();
    expect(rows[0].gainLossBase).toBeNull();
  });

  it("keeps different exchanges separate", () => {
    const rows = consolidateHoldings([
      parcel({ ticker: "Z", exchange: "ASX", quantity: 1, market_value_base: 1, cost_base_total_base: 1 }),
      parcel({ ticker: "Z", exchange: "US", quantity: 1, market_value_base: 1, cost_base_total_base: 1 }),
    ]);
    expect(rows).toHaveLength(2);
  });
});
