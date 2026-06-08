# Portfolio Tracker — Backend (Phase 1)

A lightweight Flask + SQLite backend for tracking a household investment
portfolio (ASX, US, and crypto holdings) with live price lookups via yfinance
and benchmark comparison support. The React frontend lands in Phase 2.

## Features

- SQLite database (single file in the project root, no external services)
- CSV ingestion for holdings, with per-row validation
- Live price + FX lookups via yfinance, **cached** so we don't hammer Yahoo
- Multi-currency support: AUD / USD instruments normalised to a base currency
- REST API for holdings, portfolio summary, and benchmarks

## Project layout

| File | Purpose |
|------|---------|
| `app.py` | Flask app and API endpoints |
| `models.py` | SQLAlchemy ORM models (portfolios, holdings, prices) |
| `database.py` | Engine, sessions, initialization |
| `portfolio.py` | Core logic: pricing, valuation, CSV ingestion, benchmarks |
| `config.py` | Configuration (env-overridable) |
| `requirements.txt` | Python dependencies |
| `sample_holdings.csv` / `sample_benchmarks.csv` | Example uploads |

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                       # serves on http://127.0.0.1:5000
```

The database (`portfolio.db`) and default "My Portfolio" are created on first
run.

### Configuration (optional)

All settable via environment variables — see `config.py`:

| Variable | Default | Meaning |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///portfolio.db` | SQLAlchemy DB URL |
| `BASE_CURRENCY` | `AUD` | Currency totals are reported in |
| `PRICE_CACHE_TTL_MINUTES` | `15` | How long cached prices stay fresh |
| `DEFAULT_PORTFOLIO` | `My Portfolio` | Portfolio uploads default to |

## Testing

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt   # installs pytest
pytest                                # 71 tests, runs in <1s
```

The suite is fully **offline and isolated**:

- yfinance is mocked at one seam (`portfolio._fetch_live_price`) via a
  deterministic `FakeMarket` fixture in `conftest.py` — no test hits the
  network.
- Tests run against a throwaway temp SQLite database; your real
  `portfolio.db` is never touched. Tables are reset before each test.

Coverage spans symbol resolution, CSV ingestion (validation, defaults, bad-row
handling, replace), pricing/FX/caching (including TTL expiry and
stale-if-error), the summary calculations, benchmarks, benchmark-vs-actual
comparison (period returns, FX, weighting), and every HTTP endpoint.

## CSV formats

**Holdings** (`exchange` and `cost_currency` are optional):

```csv
ticker,quantity,cost_base_per_unit,date_acquired,broker,asset_class,exchange,cost_currency
AOV,500,2.50,2023-06-15,IBKR,stock,ASX,
IQLT,100,45.20,2024-01-10,CMC,etf,CBOE_AU,
AAPL,20,150.00,2023-09-01,IBKR,stock,US,USD
BTC,0.5,30000.00,2024-02-01,IBKR,cryptocurrency,CRYPTO,
```

- `exchange` defaults to `ASX`.
- `cost_currency` is the currency you **paid** in. Leave it blank and it
  defaults to the base currency (AUD) — correct for anything you bought in AUD,
  including unhedged Cboe-AU ETFs whose AUD value floats with FX. Set it
  explicitly (e.g. `USD`) when you funded the purchase in the native currency.

**Benchmarks** (rows sharing a `name` form one benchmark):

```csv
name,ticker,weight_pct,exchange
ASX200,VAS,100,ASX
60/40 ASX/US,VAS,60,ASX
60/40 ASX/US,VGS,40,ASX
```

### Exchanges & tickers

yfinance needs exchange-qualified symbols. The `exchange` column maps to the
right symbol automatically:

| `exchange` | Example ticker | yfinance symbol | Currency |
|------------|----------------|-----------------|----------|
| `ASX` (default) | `VAS` | `VAS.AX` | AUD |
| `US` / `NASDAQ` / `NYSE` | `AAPL` | `AAPL` | USD |
| `CBOE_AU` / `CHIA` / `XA` | `IQLT` | `IQLT` | USD |
| `CRYPTO` | `BTC` | `BTC-USD` | USD |
| `RAW` | `^AXJO` | `^AXJO` | base (no FX) |

**Cboe Australia (Chi-X) ETFs** — funds like `IQLT`, `IVLU`, `IMTM` show up as
`IQLT.XA` in Apple Stocks. They are cross-quotations of the underlying
**US-listed** iShares ETFs, so `CBOE_AU` resolves to the US listing (USD) and
the value is FX-converted to AUD. Use this exchange for them; `ASX` will not
find them.

These ETFs are typically **unhedged**, so their AUD value moves with USD/AUD —
which is exactly what pricing them off the US listing (USD) and FX-converting to
AUD produces. Since you pay AUD for them, leave `cost_currency` blank (defaults
to AUD) so gain/loss is measured against what you actually paid.

## API reference

Base URL: `http://127.0.0.1:5000`

### `GET /health`
Liveness check → `{"status": "ok"}`.

### `GET /holdings`
All holdings across actual portfolios, each enriched with current price,
market value (native + base currency), cost base, and gain/loss.

### `POST /holdings/upload`
Ingest a holdings CSV. Send either a multipart `file` field or the raw CSV as
the request body.

Query/form params:
- `portfolio` — target portfolio name (default `My Portfolio`)
- `replace` — `true` to clear the portfolio's existing holdings first

```bash
curl -F "file=@sample_holdings.csv" \
     "http://127.0.0.1:5000/holdings/upload?portfolio=My%20Portfolio"
```

Response includes `added`, `skipped`, and per-row `errors` (bad rows are
skipped, not fatal).

### `GET /portfolio/summary`
Totals in base currency, gain/loss, plus breakdowns by asset class, broker, and
currency (each with weight %). Tickers that couldn't be priced are listed under
`unpriced_tickers`.

### `GET /benchmarks`
Lists benchmark portfolios with their constituents and total weight.

### `GET /benchmarks/compare`
Compares your actual portfolio's return against every benchmark over one or
more periods, **in base currency (FX-adjusted)**.

Query params:
- `periods` — comma-separated list (default `1mo,3mo,6mo,ytd,1y`). Supported:
  `1mo,3mo,6mo,ytd,1y,3y,5y`.

```bash
curl "http://127.0.0.1:5000/benchmarks/compare?periods=3mo,1y"
```

Returns, per period: the actual portfolio return, each benchmark return, and
the `excess_return_pct` (actual − benchmark). `coverage` shows how many
constituents had usable price history (e.g. `3/3`). Returns are **price
returns** (capital only) computed from the current holdings/weights — they
isolate investment performance from contribution timing, but exclude dividends.

### `POST /benchmarks/create`
Create/replace a benchmark. Two ways:

CSV upload:
```bash
curl -F "file=@sample_benchmarks.csv" http://127.0.0.1:5000/benchmarks/create
```

JSON body:
```bash
curl -H "Content-Type: application/json" \
     -d '{"name":"ASX200","constituents":[{"ticker":"VAS","weight_pct":100,"exchange":"ASX"}]}' \
     http://127.0.0.1:5000/benchmarks/create
```

A `warning` is returned if weights don't sum to 100%.

## Notes & design decisions

- **Stale-if-error pricing**: if yfinance is unreachable, the last cached price
  is used rather than failing the request. A bad ticker leaves that holding's
  values as `null` instead of breaking the whole response.
- **Currencies**: market value uses the price currency; cost base uses
  `cost_currency` (default: base currency). The two sides are FX-converted
  independently, so an AUD-paid, USD-priced unhedged ETF reports gain/loss
  correctly. FX rates (e.g. `USDAUD=X`) are fetched and cached like prices.
- **No auth** by design for Phase 1 — keep behind localhost.

## Known limitations

- **Price returns only.** Comparison and gain/loss are capital returns; they
  exclude dividends/distributions, so they understate total return for income
  funds.
- **Hedged funds.** Pricing assumes a fund's AUD value tracks its native
  (USD) price via FX — true for *unhedged* funds. A currency-*hedged* fund
  would not move with FX, so its market value would be miscalculated. None of
  the current sample holdings are hedged; flag any hedged holdings if you add
  them.

## Can I use data from the Apple Stocks app?

Short answer: no, and there's no benefit over yfinance.

- Apple's Stocks app has **no public/sanctioned API** to read quotes
  programmatically. It's a closed consumer app.
- The `.XA` suffix you see (e.g. `IQLT.XA`) is just Apple's internal exchange
  code for **Cboe Australia**. This project handles those via the `CBOE_AU`
  exchange (see above).
- Apple sources its data from commercial providers; for a local/free workflow,
  yfinance (Yahoo Finance) gives equivalent coverage for ASX, US, Cboe-AU
  cross-listings, FX, and crypto. Recommend staying with yfinance.

## Phase 2 ideas (not yet built)

- React frontend consuming this API
- Fold a compact comparison into `/portfolio/summary`
- Total-return (dividend-adjusted) performance
- Sector breakdown (yfinance `.info` enrichment)
- A scheduled background price refresher (logic in `portfolio.py` is already
  framework-agnostic to support this)
