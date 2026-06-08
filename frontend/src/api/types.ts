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
  coverage: string;
}

export interface ComparisonCell {
  actual_return_pct: number | null;
  benchmark_return_pct: number | null;
  excess_return_pct: number | null;
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
