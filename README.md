# Portfolio Tracker

A lightweight Flask + SQLite **backend** (Phase 1) for tracking a household
investment portfolio (ASX, US, Cboe-AU, and crypto holdings) with live price
lookups via yfinance and benchmark comparison, plus a React + TypeScript
**dashboard** (Phase 2) in [`frontend/`](frontend/).

> **Easiest way to run it (macOS, no terminal typing):**
> 1. Double-click **`setup.command`** once (first-time install + build).
> 2. Double-click **`start.command`** whenever you want to use the app — it
>    starts the server and opens http://127.0.0.1:5000 in your browser.
>
> Drag `start.command` to your Desktop or Dock for one-click access, and
> bookmark http://127.0.0.1:5000. Close the small terminal window (or Ctrl-C)
> to stop the app. Details under [Running the app](#running-the-app).

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
| `ledger.py` | Transaction ledger: FIFO cost base, realised gains, CGT, sync |
| `config.py` | Configuration (env-overridable) |
| `tax.py` | Australian resident income-tax estimate (for CGT) |
| `requirements.txt` | Python dependencies |
| `setup.command` / `start.command` | macOS one-click setup / launch |
| `frontend/` | React + TypeScript dashboard (built into `frontend/dist`) |
| `sample_holdings.csv` / `sample_benchmarks.csv` / `sample_transactions.csv` | Example uploads |

## Running the app

Requires Python 3.11+ and Node 18+ (for the one-time frontend build).

**macOS (one-click):** double-click `setup.command` once, then `start.command`
to launch. That's it.

**Any platform (manual):**

```bash
# one-time setup
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.txt
( cd frontend && npm install && npm run build )

# run (serves API + frontend together)
python app.py                             # http://127.0.0.1:5000
```

`app.py` serves the built React app (`frontend/dist`) at the root, so the whole
tool runs as **one process at one URL** — just open http://127.0.0.1:5000. The
database (`portfolio.db`) and default "My Portfolio" are created on first run.

> Working on the frontend? Run the Vite dev server for hot-reload
> (`cd frontend && npm run dev`, http://localhost:5173) alongside
> `FLASK_DEBUG=1 python app.py`. CORS is enabled for this.

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

**Transactions** (Phase 3 — the buy/sell ledger; `exchange`, `fee`, `reference`,
`currency` are optional):

```csv
ticker,type,quantity,price_per_unit,trade_date,exchange,fee,reference,currency
AOV,buy,500,2.50,2023-01-15,ASX,,CMC-1001,
AOV,buy,300,3.10,2023-08-01,ASX,,CMC-1002,
AOV,sell,200,4.00,2024-09-01,ASX,,CMC-1003,
AAPL,buy,20,150.00,2023-09-01,US,,IBKR-22,USD
```

`quantity` is always positive; `type` (`buy`/`sell`) sets the direction. Unlike
the holdings snapshot, this **is** a full transaction log — record every buy and
sell, and the FIFO engine derives your current parcels and realised gains. `fee`
defaults to 0 (wired through cost base, so populate it later when you have it).

**CMC "Cash Transaction Summary" export** — auto-detected on upload (no
reformatting needed). Trade rows in the `Description` (`Bght`/`Sold`) are parsed
for ticker, quantity, price, and reference; `:US` codes map to the US exchange
and known Cboe-Australia codes (IQLT/IVLU/IMTM/IVHG) to `CBOE_AU`; all other rows
(deposits, dividends, interest, transfers, balances) are skipped. Brokerage is
derived from the Debit/Credit columns when present. The file also contains
dividend/distribution rows — not used yet, but useful for future total-return
and franking work.

### Exchanges & tickers

yfinance needs exchange-qualified symbols. The `exchange` column maps to the
right symbol automatically:

| `exchange` | Example ticker | yfinance symbol | Currency |
|------------|----------------|-----------------|----------|
| `ASX` (default) | `VAS` | `VAS.AX` | AUD |
| `US` / `NASDAQ` / `NYSE` | `AAPL` | `AAPL` | USD |
| `CBOE_AU` / `CHIA` / `XA` | `IQLT` | `IQLT.XA` | AUD |
| `CRYPTO` | `BTC` | `BTC-USD` | USD |
| `RAW` | `^AXJO` | `^AXJO` | base (no FX) |

**Cboe Australia (Chi-X) ETFs** — funds like `IQLT`, `IVLU`, `IMTM`, `IVHG`.
Yahoo lists these directly with a `.XA` suffix, **priced in AUD** (e.g.
`IQLT.XA`) — the same code Apple Stocks shows. `CBOE_AU` resolves to that. Use
this exchange for them; `ASX` will not find them. (Avoid the US listing of the
same code — same index, but a different unit price.)

Since the `.XA` listing is already AUD-quoted and you pay AUD for them, leave
`cost_currency` blank (defaults to AUD).

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

### `GET /transactions`
All transactions across actual portfolios, newest trade first.

### `POST /transactions/upload`
Ingest a transactions CSV (multipart `file` or raw body). Same `portfolio` and
`replace` params as `/holdings/upload`. Bad rows are reported and skipped.

### `GET /portfolio/realised`
Realised gains via FIFO, with a CGT-discount estimate. Optional params:
`financial_year=2023-24` (Australian FY, 1 Jul–30 Jun; filters by sell date) and
`taxable_income=120000` (your income excluding gains, for a tax estimate).

```bash
curl "http://127.0.0.1:5000/portfolio/realised?financial_year=2023-24&taxable_income=120000"
```

Returns each realised event (matched buy/sell parcels, gain, and
`cgt_discount_eligible`), totals grouped by currency, and a `cgt_estimate`
(total/short-term/eligible gains, estimated 50% discount, net). When
`taxable_income` is supplied, `cgt_estimate.estimated_tax` adds the marginal tax
the net gain attracts, using FY-aware resident brackets + Medicare levy
([`tax.py`](tax.py)). **All CGT/tax figures are informational estimates, not tax
advice** — they ignore capital-loss offset ordering, carried-forward losses,
offsets, and household/partner splitting.

### `POST /transactions/sync-holdings`
Rebuilds the portfolio's holdings from the ledger's open (FIFO) parcels — one
holding row per parcel, preserving acquisition date and cost base — so the
valuation/summary/comparison views reflect your transaction history.

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
It consumes the API above and provides these tabs: **Overview** (summary cards +
allocation donut charts), **Holdings** (valued table), **Benchmarks**
(definitions), **Compare** (benchmark-vs-actual return chart + table),
**Transactions** (ledger table + CSV import + "sync holdings from ledger"),
**CGT** (FY + taxable-income controls → realised gains, discount, and estimated
tax), and **Manage** (CSV upload + a benchmark builder form).

For everyday use it's **served by Flask** (see [Running the app](#running-the-app))
— `python app.py` builds nothing, it just serves `frontend/dist`. For frontend
development with hot-reload:

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (expects the backend on :5000)
```

Other scripts: `npm run build` (typecheck + production build — run after any
frontend change so the served app updates), `npm test` (Vitest unit tests),
`npm run preview` (serve the build).

- The API base URL defaults to `http://127.0.0.1:5000`; override with a
  `VITE_API_URL` env var. It uses the IPv4 loopback rather than `localhost`
  because Flask binds `127.0.0.1` and `localhost` can resolve to IPv6 `::1` first.
- CORS is enabled so the dev server can call the API cross-origin.

> If `npm install` fails with an `EACCES` cache error, your global npm cache has
> root-owned files; run with a writable cache, e.g.
> `NPM_CONFIG_CACHE=/tmp/npm-cache npm install`.

## Known limitations

- **Price returns only.** Comparison and gain/loss are capital returns; they
  exclude dividends/distributions, so they understate total return for income
  funds.
- **Tickers yfinance can't price.** A few codes have no Yahoo quote (e.g.
  delisted/renamed funds like `VGMF`); they show as unpriced rather than
  guessed. New Cboe-Australia codes also need adding to `CBOE_AU_TICKERS` in
  `ledger.py` (or set `exchange=CBOE_AU` in the CSV) so they resolve to `.XA`.
  A per-ticker manual price override is a planned fallback.

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

## Phase 3: transaction ledger & CGT (backend built)

A `transactions` table (buys **and** sells) with a FIFO cost-base engine
([`ledger.py`](ledger.py)) powers realised-gain and CGT reporting:

- **FIFO** matching (oldest parcels sold first); fees wired through (default 0).
- **Realised gains** per matched parcel, with Australian-FY filtering.
- **CGT discount**: parcels held > 12 months flagged for the 50% discount; a
  simplified net-gain estimate (with caveats — not tax advice).
- **Tax estimate**: with an optional taxable-income input, estimates the
  marginal tax the net gain attracts (FY-aware resident brackets + Medicare
  levy — see [`tax.py`](tax.py)).
- **Sync to holdings**: derive current parcels from the ledger into
  `portfolio_holdings`, so all existing views work off your real trade history.

Surfaced in the **Transactions** and **CGT** frontend tabs and the
`/transactions/*` / `/portfolio/realised` endpoints above.

> **Future:** the 50% CGT discount is expected to be replaced by an
> inflation/indexation method. When that lands, the discount logic in
> `ledger.py` (and the net gain fed into `tax.py`) will need a new calculation
> path; the marginal-tax step is unaffected. Not modelled yet. Also pending:
> per-trade-date FX for exact AUD CGT on foreign-currency trades.

## Other ideas (not yet built)

- Fold a compact comparison into `/portfolio/summary`
- Total-return (dividend-adjusted) performance
- Sector breakdown (yfinance `.info` enrichment)
- A scheduled background price refresher (logic in `portfolio.py` is already
  framework-agnostic to support this)
