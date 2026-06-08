"""Core business logic: symbol resolution, price/FX caching, valuation,
CSV ingestion, and benchmark creation.

This module is deliberately framework-agnostic (no Flask imports) so the logic
can be unit-tested and reused by future workers (e.g. a scheduled price
refresher) independently of the web layer.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field

import yfinance as yf
from sqlalchemy.orm import Session

import config
from database import ensure_portfolio
from models import Holding, Portfolio, Price, utcnow


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class PortfolioError(Exception):
    """Base class for expected, user-facing errors (mapped to HTTP 400)."""


class PriceLookupError(PortfolioError):
    pass


# --------------------------------------------------------------------------- #
# Symbol resolution
# --------------------------------------------------------------------------- #
# yfinance uses suffixes to disambiguate exchanges. We map our friendly
# `exchange` values to the suffix and the instrument's native trading currency.
_EXCHANGE = {
    "ASX": {"suffix": ".AX", "currency": "AUD"},
    "US": {"suffix": "", "currency": "USD"},
    "NASDAQ": {"suffix": "", "currency": "USD"},
    "NYSE": {"suffix": "", "currency": "USD"},
    # Cboe Australia (formerly Chi-X; shown as e.g. IQLT.XA in Apple Stocks)
    # cross-quotes US-listed ETFs. We price off the underlying US listing in
    # USD and FX-convert to the base currency, which matches their AUD value.
    "CBOE_AU": {"suffix": "", "currency": "USD"},
    "CHIA": {"suffix": "", "currency": "USD"},
    "XA": {"suffix": "", "currency": "USD"},
    "CRYPTO": {"suffix": "-USD", "currency": "USD"},
    # Pass-through for raw Yahoo symbols such as indices (e.g. ^AXJO). Currency
    # is unknown, so it is treated as the base currency (no FX conversion).
    "RAW": {"suffix": "", "currency": None},
}
DEFAULT_EXCHANGE = "ASX"


def resolve_symbol(ticker: str, exchange: str | None) -> tuple[str, str]:
    """Return ``(yfinance_symbol, native_currency)`` for a ticker/exchange."""
    ex = (exchange or DEFAULT_EXCHANGE).upper()
    info = _EXCHANGE.get(ex, _EXCHANGE[DEFAULT_EXCHANGE])
    base = ticker.strip().upper()
    if ex == "CRYPTO":
        symbol = f"{base}-USD"
    else:
        symbol = f"{base}{info['suffix']}"
    return symbol, info["currency"]


# --------------------------------------------------------------------------- #
# Price / FX lookup + caching
# --------------------------------------------------------------------------- #
def _fetch_live_price(symbol: str) -> tuple[float, str | None]:
    """Fetch the latest price for a resolved symbol from yfinance.

    Tries the cheap ``fast_info`` path first and falls back to recent history.
    Raises :class:`PriceLookupError` if no price can be determined.
    """
    ticker = yf.Ticker(symbol)

    price: float | None = None
    currency: str | None = None

    try:
        fast = dict(ticker.fast_info)
        currency = fast.get("currency") or fast.get("last_price_currency")
        for key in ("lastPrice", "last_price", "regularMarketPrice"):
            if fast.get(key) is not None:
                price = float(fast[key])
                break
    except Exception:
        pass

    if price is None:
        try:
            hist = ticker.history(period="5d")
            closes = hist["Close"].dropna() if not hist.empty else []
            if len(closes):
                price = float(closes.iloc[-1])
        except Exception:
            pass

    if price is None:
        raise PriceLookupError(f"No price available for '{symbol}'")
    return price, currency


def _get_or_refresh_symbol(
    session: Session, symbol: str, default_currency: str | None = None
) -> Price | None:
    """Return a cached :class:`Price` for ``symbol``, refreshing if stale.

    On lookup failure, a previously cached (stale) row is returned if present,
    so a transient yfinance outage degrades gracefully instead of erroring.
    Returns ``None`` only when there is no cached value and the live lookup
    fails.
    """
    now = utcnow()
    ttl = dt.timedelta(minutes=config.PRICE_CACHE_TTL_MINUTES)
    row = session.query(Price).filter_by(ticker=symbol).one_or_none()

    if row is not None and row.last_updated and (now - row.last_updated) < ttl:
        return row

    try:
        price, currency = _fetch_live_price(symbol)
    except PriceLookupError:
        return row  # stale-if-error (may be None)

    currency = currency or default_currency
    if row is None:
        row = Price(ticker=symbol, price=price, currency=currency, last_updated=now)
        session.add(row)
    else:
        row.price = price
        row.currency = currency
        row.last_updated = now
    session.flush()
    return row


def get_fx_rate(
    session: Session, currency: str | None, base: str | None = None
) -> float | None:
    """Units of ``base`` per 1 unit of ``currency`` (e.g. AUD per 1 USD)."""
    base = base or config.BASE_CURRENCY
    if not currency or currency == base:
        return 1.0
    row = _get_or_refresh_symbol(session, f"{currency}{base}=X", base)
    return row.price if row else None


# --------------------------------------------------------------------------- #
# Valuation
# --------------------------------------------------------------------------- #
def value_holding(session: Session, holding: Holding) -> dict:
    """Return a holding enriched with current price and valuation in base ccy.

    Cost base is assumed to be expressed in the instrument's native currency.
    Any value that can't be computed (e.g. missing price) is returned as None
    rather than raising, so one bad ticker doesn't break the whole response.
    """
    symbol, native_currency = resolve_symbol(holding.ticker, holding.exchange)
    price_row = _get_or_refresh_symbol(session, symbol, native_currency)

    price = price_row.price if price_row else None
    currency = (price_row.currency if price_row else None) or native_currency
    fx = get_fx_rate(session, currency)
    qty = holding.quantity or 0.0

    market_value_native = price * qty if price is not None else None
    market_value_base = (
        market_value_native * fx
        if (market_value_native is not None and fx is not None)
        else None
    )

    # Cost base may be recorded in a different currency than the price. An AUD
    # investor who paid AUD for an (unhedged) USD-priced ETF has an AUD cost
    # base but a USD-priced market value, so the two sides use separate FX.
    cost_currency = holding.cost_currency or config.BASE_CURRENCY
    cost_fx = get_fx_rate(session, cost_currency)
    cost_total_native = (
        holding.cost_base_per_unit * qty
        if holding.cost_base_per_unit is not None
        else None
    )
    cost_total_base = (
        cost_total_native * cost_fx
        if (cost_total_native is not None and cost_fx is not None)
        else None
    )

    gain = (
        market_value_base - cost_total_base
        if (market_value_base is not None and cost_total_base is not None)
        else None
    )
    gain_pct = (
        (gain / cost_total_base * 100.0)
        if (gain is not None and cost_total_base)
        else None
    )

    result = holding.to_dict()
    result.update(
        {
            "symbol": symbol,
            "current_price": price,
            "price_currency": currency,
            "price_last_updated": price_row.last_updated.isoformat()
            if price_row and price_row.last_updated
            else None,
            "fx_rate_to_base": fx,
            "market_value": market_value_native,
            "market_value_base": market_value_base,
            "cost_base_total": cost_total_native,
            "cost_base_currency": cost_currency,
            "cost_base_total_base": cost_total_base,
            "gain_loss_base": gain,
            "gain_loss_pct": gain_pct,
            "base_currency": config.BASE_CURRENCY,
        }
    )
    return result


def get_actual_holdings(session: Session) -> list[dict]:
    """All holdings across actual (non-benchmark) portfolios, valued."""
    holdings = (
        session.query(Holding)
        .join(Portfolio)
        .filter(Portfolio.type == "actual")
        .all()
    )
    return [value_holding(session, h) for h in holdings]


def portfolio_summary(session: Session) -> dict:
    """Totals plus breakdowns by asset class, broker, and currency."""
    valued = get_actual_holdings(session)

    total_value = 0.0
    total_cost = 0.0
    priced = 0
    unpriced: list[str] = []

    by_asset_class: dict[str, float] = {}
    by_broker: dict[str, float] = {}
    by_currency: dict[str, float] = {}

    for h in valued:
        mv = h["market_value_base"]
        if mv is None:
            unpriced.append(h["ticker"])
            continue
        priced += 1
        total_value += mv
        if h["cost_base_total_base"] is not None:
            total_cost += h["cost_base_total_base"]

        ac = h.get("asset_class") or "unknown"
        broker = h.get("broker") or "unknown"
        ccy = h.get("price_currency") or "unknown"
        by_asset_class[ac] = by_asset_class.get(ac, 0.0) + mv
        by_broker[broker] = by_broker.get(broker, 0.0) + mv
        by_currency[ccy] = by_currency.get(ccy, 0.0) + mv

    gain = total_value - total_cost if total_cost else None
    gain_pct = (gain / total_cost * 100.0) if (gain is not None and total_cost) else None

    def _weighted(d: dict[str, float]) -> list[dict]:
        return [
            {
                "key": k,
                "value": round(v, 2),
                "weight_pct": round(v / total_value * 100.0, 2)
                if total_value
                else None,
            }
            for k, v in sorted(d.items(), key=lambda kv: kv[1], reverse=True)
        ]

    return {
        "base_currency": config.BASE_CURRENCY,
        "total_market_value": round(total_value, 2),
        "total_cost_base": round(total_cost, 2),
        "total_gain_loss": round(gain, 2) if gain is not None else None,
        "total_gain_loss_pct": round(gain_pct, 2) if gain_pct is not None else None,
        "holdings_count": len(valued),
        "holdings_priced": priced,
        "unpriced_tickers": unpriced,
        "by_asset_class": _weighted(by_asset_class),
        "by_broker": _weighted(by_broker),
        "by_currency": _weighted(by_currency),
    }


# --------------------------------------------------------------------------- #
# CSV ingestion
# --------------------------------------------------------------------------- #
@dataclass
class IngestResult:
    added: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)
    portfolio: str = ""

    def as_dict(self) -> dict:
        return {
            "portfolio": self.portfolio,
            "added": self.added,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def _decode_csv(raw: bytes | str) -> csv.DictReader:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    return csv.DictReader(io.StringIO(text))


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _upper_or_none(value: str | None) -> str | None:
    cleaned = _clean(value)
    return cleaned.upper() if cleaned else None


def ingest_holdings_csv(
    session: Session,
    raw: bytes | str,
    portfolio_name: str | None = None,
    replace: bool = False,
) -> IngestResult:
    """Ingest a holdings CSV into an actual portfolio.

    Expected columns: ticker, quantity, cost_base_per_unit, date_acquired,
    broker, asset_class, and (optional) exchange. Rows are validated
    individually; a bad row is recorded in ``errors`` and skipped rather than
    aborting the whole upload.
    """
    name = portfolio_name or config.DEFAULT_PORTFOLIO
    portfolio = ensure_portfolio(session, name, "actual")
    result = IngestResult(portfolio=name)

    reader = _decode_csv(raw)
    if reader.fieldnames is None or "ticker" not in {
        f.strip().lower() for f in (reader.fieldnames or [])
    }:
        raise PortfolioError(
            "CSV must include a 'ticker' column. "
            "Expected header: ticker,quantity,cost_base_per_unit,"
            "date_acquired,broker,asset_class[,exchange]"
        )

    if replace:
        # delete-orphan cascade removes the cleared holdings on flush.
        portfolio.holdings.clear()
        session.flush()

    # ``enumerate`` from 2 so row numbers match what a human sees in a
    # spreadsheet (row 1 is the header).
    for line_no, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): v for k, v in row.items()}
        ticker = _clean(row.get("ticker"))
        if not ticker:
            result.skipped += 1
            result.errors.append({"row": line_no, "error": "missing ticker"})
            continue

        try:
            quantity = _parse_float(row.get("quantity"), "quantity", required=True)
            cost = _parse_float(row.get("cost_base_per_unit"), "cost_base_per_unit")
            date_acquired = _parse_date(row.get("date_acquired"))
        except PortfolioError as exc:
            result.skipped += 1
            result.errors.append({"row": line_no, "error": str(exc)})
            continue

        # Append through the relationship so the in-session collection stays
        # consistent (the FK is set from the parent automatically).
        portfolio.holdings.append(
            Holding(
                ticker=ticker.upper(),
                exchange=(_clean(row.get("exchange")) or DEFAULT_EXCHANGE).upper(),
                quantity=quantity,
                cost_base_per_unit=cost,
                cost_currency=_upper_or_none(row.get("cost_currency")),
                date_acquired=date_acquired,
                broker=_clean(row.get("broker")),
                asset_class=(_clean(row.get("asset_class")) or "stock"),
            )
        )
        result.added += 1

    session.flush()
    return result


def _parse_float(
    value: str | None, field_name: str, required: bool = False
) -> float | None:
    value = _clean(value)
    if value is None:
        if required:
            raise PortfolioError(f"missing {field_name}")
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        raise PortfolioError(f"invalid {field_name}: '{value}'")


def _parse_date(value: str | None) -> dt.date | None:
    value = _clean(value)
    if value is None:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise PortfolioError(f"invalid date_acquired: '{value}' (use YYYY-MM-DD)")


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #
def list_benchmarks(session: Session) -> list[dict]:
    benchmarks = (
        session.query(Portfolio).filter(Portfolio.type == "benchmark").all()
    )
    out = []
    for bench in benchmarks:
        constituents = [
            {
                "ticker": h.ticker,
                "exchange": h.exchange,
                "weight_pct": h.weight_pct,
            }
            for h in bench.holdings
        ]
        out.append(
            {
                **bench.to_dict(),
                "constituents": constituents,
                "total_weight_pct": round(
                    sum(c["weight_pct"] or 0 for c in constituents), 2
                ),
            }
        )
    return out


def create_benchmark_from_csv(session: Session, raw: bytes | str) -> list[dict]:
    """Create one or more benchmarks from a CSV.

    Columns: name, ticker, weight_pct, and (optional) exchange. Rows sharing a
    name are grouped into a single benchmark portfolio.
    """
    reader = _decode_csv(raw)
    headers = {f.strip().lower() for f in (reader.fieldnames or [])}
    required = {"name", "ticker", "weight_pct"}
    if not required.issubset(headers):
        raise PortfolioError(
            f"Benchmark CSV must include columns: {', '.join(sorted(required))}"
        )

    grouped: dict[str, list[dict]] = {}
    for line_no, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): v for k, v in row.items()}
        name = _clean(row.get("name"))
        ticker = _clean(row.get("ticker"))
        if not name or not ticker:
            raise PortfolioError(f"row {line_no}: name and ticker are required")
        weight = _parse_float(row.get("weight_pct"), "weight_pct", required=True)
        grouped.setdefault(name, []).append(
            {
                "ticker": ticker.upper(),
                "exchange": (_clean(row.get("exchange")) or DEFAULT_EXCHANGE).upper(),
                "weight_pct": weight,
            }
        )

    return [
        _upsert_benchmark(session, name, constituents)
        for name, constituents in grouped.items()
    ]


def create_benchmark_from_dict(session: Session, payload: dict) -> dict:
    """Create a benchmark from a JSON body.

    Shape: ``{"name": str, "constituents": [{"ticker", "weight_pct",
    "exchange"?}]}``.
    """
    name = _clean(payload.get("name"))
    constituents = payload.get("constituents") or payload.get("holdings")
    if not name or not constituents:
        raise PortfolioError("Benchmark requires 'name' and non-empty 'constituents'")

    cleaned = []
    for c in constituents:
        ticker = _clean(str(c.get("ticker", "")))
        if not ticker:
            raise PortfolioError("each constituent needs a 'ticker'")
        if c.get("weight_pct") is None:
            raise PortfolioError(f"{ticker}: missing 'weight_pct'")
        cleaned.append(
            {
                "ticker": ticker.upper(),
                "exchange": (str(c.get("exchange") or DEFAULT_EXCHANGE)).upper(),
                "weight_pct": float(c["weight_pct"]),
            }
        )
    return _upsert_benchmark(session, name, cleaned)


def _upsert_benchmark(
    session: Session, name: str, constituents: list[dict]
) -> dict:
    """Create or replace a benchmark portfolio and its constituents."""
    portfolio = session.query(Portfolio).filter_by(name=name).one_or_none()
    if portfolio is not None and portfolio.type != "benchmark":
        raise PortfolioError(
            f"'{name}' already exists as an actual portfolio; choose another name"
        )
    if portfolio is None:
        portfolio = Portfolio(name=name, type="benchmark")
        session.add(portfolio)

    # Assigning the collection replaces any existing constituents; the
    # delete-orphan cascade removes the old rows on flush.
    portfolio.holdings = [
        Holding(
            ticker=c["ticker"],
            exchange=c["exchange"],
            weight_pct=c["weight_pct"],
        )
        for c in constituents
    ]
    session.flush()
    total_weight = sum(c["weight_pct"] for c in constituents)

    result = {
        **portfolio.to_dict(),
        "constituents": constituents,
        "total_weight_pct": round(total_weight, 2),
    }
    if abs(total_weight - 100.0) > 0.01:
        result["warning"] = (
            f"weights sum to {round(total_weight, 2)}%, not 100%"
        )
    return result


# --------------------------------------------------------------------------- #
# Benchmark vs. actual comparison
# --------------------------------------------------------------------------- #
# yfinance period strings we support for the comparison endpoint.
SUPPORTED_PERIODS = ("1mo", "3mo", "6mo", "ytd", "1y", "3y", "5y")
DEFAULT_PERIODS = ("1mo", "3mo", "6mo", "ytd", "1y")


def _fetch_close_series(symbol: str, period: str):
    """Return a pandas Series of daily closes for ``symbol`` over ``period``.

    This is the single network seam for historical data (mocked in tests).
    Returns ``None`` if no usable history is available.
    """
    try:
        hist = yf.Ticker(symbol).history(period=period)
    except Exception:
        return None
    if hist is None or hist.empty or "Close" not in hist:
        return None
    closes = hist["Close"].dropna()
    return closes if len(closes) else None


def _period_return(
    symbol: str, currency: str | None, period: str, base: str
) -> float | None:
    """Fractional total price return of ``symbol`` over ``period``, in ``base``.

    If the instrument trades in a non-base currency, the start/end prices are
    converted using the FX rate at each endpoint so the return reflects what an
    investor in ``base`` actually experienced (price move + currency move).
    """
    closes = _fetch_close_series(symbol, period)
    if closes is None or len(closes) < 2:
        return None
    start = float(closes.iloc[0])
    end = float(closes.iloc[-1])
    if start == 0:
        return None

    if not currency or currency == base:
        return end / start - 1.0

    fx = _fetch_close_series(f"{currency}{base}=X", period)
    if fx is None or len(fx) < 2:
        # Fall back to the native-currency return rather than failing.
        return end / start - 1.0
    start_fx = float(fx.iloc[0])
    end_fx = float(fx.iloc[-1])
    if start_fx == 0:
        return end / start - 1.0
    return (end * end_fx) / (start * start_fx) - 1.0


def _weighted_period_returns(
    components: list[tuple[float | None, dict[str, float | None]]],
    periods,
) -> dict[str, dict]:
    """Weight per-component returns into a single return per period.

    ``components`` is a list of ``(weight, {period: return})``. For each period
    we average the available component returns by weight, renormalising over the
    components that actually have data (so one missing price doesn't zero out the
    period). ``coverage`` reports how many components contributed.
    """
    out: dict[str, dict] = {}
    for period in periods:
        weighted_sum = 0.0
        weight_total = 0.0
        contributing = 0
        for weight, returns in components:
            r = returns.get(period)
            if r is None or weight is None:
                continue
            weighted_sum += weight * r
            weight_total += weight
            contributing += 1
        out[period] = {
            "return_pct": round(weighted_sum / weight_total * 100.0, 2)
            if weight_total
            else None,
            "coverage": f"{contributing}/{len(components)}",
        }
    return out


def _actual_period_returns(session: Session, periods) -> dict[str, dict]:
    """Return of the current actual holdings, weighted by market value."""
    base = config.BASE_CURRENCY
    holdings = (
        session.query(Holding)
        .join(Portfolio)
        .filter(Portfolio.type == "actual")
        .all()
    )
    components: list[tuple[float | None, dict[str, float | None]]] = []
    for h in holdings:
        symbol, currency = resolve_symbol(h.ticker, h.exchange)
        weight = value_holding(session, h)["market_value_base"]
        returns = {p: _period_return(symbol, currency, p, base) for p in periods}
        components.append((weight, returns))
    return _weighted_period_returns(components, periods)


def _benchmark_period_returns(
    session: Session, benchmark: Portfolio, periods
) -> dict[str, dict]:
    """Return of a benchmark, weighted by its target weights."""
    base = config.BASE_CURRENCY
    components: list[tuple[float | None, dict[str, float | None]]] = []
    for c in benchmark.holdings:
        symbol, currency = resolve_symbol(c.ticker, c.exchange)
        returns = {p: _period_return(symbol, currency, p, base) for p in periods}
        components.append((c.weight_pct, returns))
    return _weighted_period_returns(components, periods)


def compare_to_benchmarks(session: Session, periods=None) -> dict:
    """Compare actual-portfolio returns to every benchmark over each period.

    Returns the actual portfolio's return, each benchmark's return, and the
    excess (actual − benchmark) per period, all in the base currency.
    """
    periods = tuple(periods) if periods else DEFAULT_PERIODS
    actual = _actual_period_returns(session, periods)

    benchmarks = (
        session.query(Portfolio).filter(Portfolio.type == "benchmark").all()
    )
    results = []
    for bench in benchmarks:
        bench_returns = _benchmark_period_returns(session, bench, periods)
        comparison = {}
        for period in periods:
            a = actual[period]["return_pct"]
            b = bench_returns[period]["return_pct"]
            comparison[period] = {
                "actual_return_pct": a,
                "benchmark_return_pct": b,
                "excess_return_pct": round(a - b, 2)
                if (a is not None and b is not None)
                else None,
                "benchmark_coverage": bench_returns[period]["coverage"],
            }
        results.append(
            {
                "id": bench.id,
                "name": bench.name,
                "periods": comparison,
            }
        )

    return {
        "base_currency": config.BASE_CURRENCY,
        "periods": list(periods),
        "actual": actual,
        "benchmarks": results,
    }
