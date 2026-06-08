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
pytest                                # 52 tests, runs in <1s
```

The suite is fully **offline and isolated**:

- yfinance is mocked at one seam (`portfolio._fetch_live_price`) via a
  deterministic `FakeMarket` fixture in `conftest.py` — no test hits the
  network.
- Tests run against a throwaway temp SQLite database; your real
  `portfolio.db` is never touched. Tables are reset before each test.

Coverage spans symbol resolution, CSV ingestion (validation, defaults, bad-row
handling, replace), pricing/FX/caching (including TTL expiry and
stale-if-error), the summary calculations, benchmarks, and every HTTP endpoint.

## CSV formats

**Holdings** (`exchange` is optional, defaults to `ASX`):

```csv
ticker,quantity,cost_base_per_unit,date_acquired,broker,asset_class,exchange
AOV,500,2.50,2023-06-15,IBKR,stock,ASX
AAPL,20,150.00,2023-09-01,IBKR,stock,US
BTC,0.5,30000.00,2024-02-01,IBKR,cryptocurrency,CRYPTO
```

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
| `CRYPTO` | `BTC` | `BTC-USD` | USD |

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
- **Currencies**: cost base is assumed to be in the instrument's native
  currency. FX rates (e.g. `USDAUD=X`) are fetched and cached like prices.
- **No auth** by design for Phase 1 — keep behind localhost.

## Phase 2 ideas (not yet built)

- React frontend consuming this API
- Benchmark-vs-actual comparison in the summary endpoint
- Sector breakdown (yfinance `.info` enrichment) and historical performance
- A scheduled background price refresher (logic in `portfolio.py` is already
  framework-agnostic to support this)
