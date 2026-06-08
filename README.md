# Portfolio Tracker

A lightweight Flask + SQLite **backend** (Phase 1) for tracking a household
investment portfolio (ASX, US, Cboe-AU, and crypto holdings) with live price
lookups via yfinance and benchmark comparison, plus a React + TypeScript
**dashboard** (Phase 2) in [`frontend/`](frontend/).

> **Quick start (both halves):** run the backend (`python app.py`), then in
> another terminal `cd frontend && npm install && npm run dev` and open
> http://localhost:5173. See [Frontend](#frontend-phase-2) below.

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

#### A holdings CSV is a snapshot of current positions — not a transaction log

Each row is **a parcel you currently hold**. Values are computed as
`current_price × quantity` and `cost_base_per_unit × quantity`, then summed.

- **Bought the same ticker over time?** Use **one row per parcel**, each with its
  own `quantity`, `cost_base_per_unit`, and `date_acquired`. They're summed for
  totals while keeping per-parcel cost/date:

  ```csv
  AOV,500,2.50,2023-01-01,IBKR,stock,ASX,
  AOV,300,3.10,2023-06-01,IBKR,stock,ASX,
  ```

- **Sold something?** Don't add sell rows or negative quantities. Record what you
  **still hold** — reduce that parcel's `quantity`, or remove the row if you
  exited. There is currently no realised-gain / sell tracking (see "Phase 3" for
  a planned transaction ledger).

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

## Frontend (Phase 2)

A React + TypeScript dashboard (Vite, recharts) lives in [`frontend/`](frontend/).
It consumes the API above and provides five tabs: **Overview** (summary cards +
allocation donut charts), **Holdings** (valued table), **Benchmarks**
(definitions), **Compare** (benchmark-vs-actual return chart + table), and
**Manage** (CSV upload + a benchmark builder form).

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (expects the backend on :5000)
```

Other scripts: `npm run build` (typecheck + production build), `npm test`
(Vitest unit tests for the formatters), `npm run preview` (serve the build).

- The API base URL defaults to `http://127.0.0.1:5000`; override with a
  `VITE_API_URL` env var (e.g. in `frontend/.env`) if the backend runs
  elsewhere. It uses the IPv4 loopback rather than `localhost` because Flask
  binds `127.0.0.1` and `localhost` can resolve to IPv6 `::1` first.
- CORS is enabled on the backend, so the dev server calls the API directly.

> If `npm install` fails with an `EACCES` cache error, your global npm cache has
> root-owned files; run with a writable cache, e.g.
> `NPM_CONFIG_CACHE=/tmp/npm-cache npm install`.

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

## Phase 3: transaction ledger & CGT (planned)

The current model tracks *current positions* (parcels), not transactions. A
planned next phase adds a `transactions` table (buys **and** sells) and derives
holdings from it, enabling:

- Realised gains on sells, with a cost-base method (FIFO / average)
- Australian CGT support: parcel-level cost base and the 12-month 50% discount
- A transaction history view and import

The schema already stores per-parcel `date_acquired` and `cost_base_per_unit`,
which feed straight into this.

## Other ideas (not yet built)

- Fold a compact comparison into `/portfolio/summary`
- Total-return (dividend-adjusted) performance
- Sector breakdown (yfinance `.info` enrichment)
- A scheduled background price refresher (logic in `portfolio.py` is already
  framework-agnostic to support this)
