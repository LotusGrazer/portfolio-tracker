// TypeScript mirrors of the Flask API response shapes (see backend portfolio.py).

export interface Holding {
  id: number;
  portfolio_id: number;
  ticker: string;
  exchange: string | null;
  quantity: number | null;
  cost_base_per_unit: number | null;
  cost_currency: string | null;
  date_acquired: string | null;
  broker: string | null;
  asset_class: string | null;
  weight_pct: number | null;
  // Enrichment from value_holding:
  symbol: string;
  current_price: number | null;
  price_currency: string | null;
  price_last_updated: string | null;
  fx_rate_to_base: number | null;
  market_value: number | null;
  market_value_base: number | null;
  cost_base_total: number | null;
  cost_base_currency: string | null;
  cost_base_total_base: number | null;
  gain_loss_base: number | null;
  gain_loss_pct: number | null;
  base_currency: string;
}

export interface Breakdown {
  key: string;
  value: number;
  weight_pct: number | null;
}

export interface Summary {
  base_currency: string;
  total_market_value: number;
  total_cost_base: number;
  total_gain_loss: number | null;
  total_gain_loss_pct: number | null;
  holdings_count: number;
  holdings_priced: number;
  unpriced_tickers: string[];
  by_asset_class: Breakdown[];
  by_broker: Breakdown[];
  by_currency: Breakdown[];
}

export interface Constituent {
  ticker: string;
  exchange: string | null;
  weight_pct: number | null;
}

export interface Benchmark {
  id: number;
  name: string;
  type: string;
  created_date: string | null;
  constituents: Constituent[];
  total_weight_pct: number;
  warning?: string;
}

export interface PeriodReturn {
  return_pct: number | null;
  // CAGR over the series' actual span; null for sub-year periods (and when
  // the span is unknown), where annualising would just amplify noise.
  annualised_return_pct: number | null;
  coverage: string;
}

export interface ComparisonCell {
  actual_return_pct: number | null;
  benchmark_return_pct: number | null;
  excess_return_pct: number | null;
  actual_annualised_return_pct: number | null;
  benchmark_annualised_return_pct: number | null;
  excess_annualised_return_pct: number | null;
  benchmark_coverage: string;
}

export interface BenchmarkComparison {
  id: number;
  name: string;
  periods: Record<string, ComparisonCell>;
}

export interface Comparison {
  base_currency: string;
  periods: string[];
  actual: Record<string, PeriodReturn>;
  benchmarks: BenchmarkComparison[];
}

export interface UploadResult {
  portfolio: string;
  added: number;
  skipped: number;
  errors: { row: number; error: string }[];
}

export interface Transaction {
  id: number;
  portfolio_id: number;
  ticker: string;
  exchange: string | null;
  type: string; // "buy" | "sell"
  quantity: number;
  price_per_unit: number;
  currency: string | null;
  fee: number;
  trade_date: string | null;
  reference: string | null;
}

export interface RealisedEvent {
  ticker: string;
  quantity: number;
  buy_date: string;
  sell_date: string;
  proceeds: number;
  cost_base: number;
  gain: number;
  currency: string | null;
  cgt_discount_eligible: boolean;
}

export interface EstimatedTax {
  taxable_income: number;
  financial_year_basis: string;
  additional_tax: number;
  effective_rate_on_gain_pct: number;
}

export interface CgtEstimate {
  total_realised_gain: number;
  discount_eligible_gain: number;
  short_term_gain: number;
  estimated_discount: number;
  estimated_net_capital_gain: number;
  disclaimer: string;
  estimated_tax?: EstimatedTax;
}

export interface Realised {
  base_currency: string;
  financial_year: string | null;
  events: RealisedEvent[];
  by_currency: Record<
    string,
    { proceeds: number; cost_base: number; gain: number }
  >;
  cgt_estimate: CgtEstimate;
  warnings: string[];
}

export interface SyncResult {
  portfolio: string;
  holdings_created: number;
  tickers: string[];
  warnings: string[];
}
