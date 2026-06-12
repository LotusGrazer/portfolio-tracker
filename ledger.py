"""Transaction ledger: FIFO cost-base accounting, realised gains, and CGT.

The FIFO engine (``fifo_process``) is a pure function over a ticker's
transactions — no database, no framework — so it is trivially testable. The
DB-facing helpers wrap it for CSV import, realised-gain reporting, and deriving
current parcels back into ``portfolio_holdings``.

Notes / scope (v1):
  * **FIFO** cost base (oldest parcels sold first).
  * **Fees** are wired through (cost += buy fee, proceeds -= sell fee) but
    default to 0, so they have no effect until populated.
  * **CGT discount eligibility** = asset held > 12 months (Australian 50%
    discount). The realised summary is an informational estimate, not tax
    advice — it does not model capital-loss offset ordering or carried-forward
    losses.
  * Realised gains are computed in each transaction's currency (a parcel's buy
    and sell share the instrument's currency). For AUD-settled trades this is
    exact for Australian CGT; cross-currency CGT in AUD would need trade-date FX
    (a future enhancement).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

import config
import tax
from database import ensure_portfolio
from models import Holding, Portfolio, Transaction
from portfolio import (
    DEFAULT_EXCHANGE,
    PortfolioError,
    _clean,
    _parse_date,
    _parse_float,
    _upper_or_none,
)

BUY = "buy"
SELL = "sell"

# Tickers that are Cboe Australia (Chi-X) listings, which CMC lists as plain
# AUD-priced codes. Mapped to the CBOE_AU exchange (Yahoo ".XA" suffix) so
# pricing resolves correctly. Other bare codes default to ASX. Extend as needed.
CBOE_AU_TICKERS = {"IQLT", "IVLU", "IMTM", "IVHG"}


# --------------------------------------------------------------------------- #
# FIFO engine (pure)
# --------------------------------------------------------------------------- #
@dataclass
class Leg:
    """One transaction as seen by the engine."""

    type: str  # BUY | SELL
    quantity: float
    price_per_unit: float
    trade_date: dt.date
    fee: float = 0.0
    currency: str | None = None


@dataclass
class Parcel:
    """An open (unsold) buy parcel, FIFO-consumed by later sells."""

    quantity: float
    price_per_unit: float
    fee_per_unit: float
    trade_date: dt.date
    currency: str | None

    @property
    def cost_base(self) -> float:
        return self.quantity * (self.price_per_unit + self.fee_per_unit)


@dataclass
class RealisedEvent:
    ticker: str
    quantity: float
    buy_date: dt.date
    sell_date: dt.date
    proceeds: float
    cost_base: float
    currency: str | None
    cgt_discount_eligible: bool

    @property
    def gain(self) -> float:
        return self.proceeds - self.cost_base

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "quantity": self.quantity,
            "buy_date": self.buy_date.isoformat(),
            "sell_date": self.sell_date.isoformat(),
            "proceeds": round(self.proceeds, 2),
            "cost_base": round(self.cost_base, 2),
            "gain": round(self.gain, 2),
            "currency": self.currency,
            "cgt_discount_eligible": self.cgt_discount_eligible,
        }


def _one_year_after(d: dt.date) -> dt.date:
    """The calendar anniversary of ``d`` (29 Feb maps to 28 Feb)."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def fifo_process(
    ticker: str, legs: list[Leg]
) -> tuple[list[RealisedEvent], list[Parcel]]:
    """Run FIFO over a ticker's legs.

    Returns ``(realised_events, open_parcels)``. Raises ``PortfolioError`` if a
    sell exceeds the quantity currently held (an oversell).

    Same-day legs process buys before sells (a same-day buy+sell would
    otherwise oversell depending on input order); ties beyond that keep input
    order, so callers should pass legs in insertion (id) order.
    """
    ordered = sorted(legs, key=lambda lg: (lg.trade_date, lg.type != BUY))
    open_parcels: list[Parcel] = []
    realised: list[RealisedEvent] = []

    for leg in ordered:
        if leg.type == BUY:
            open_parcels.append(
                Parcel(
                    quantity=leg.quantity,
                    price_per_unit=leg.price_per_unit,
                    fee_per_unit=(leg.fee / leg.quantity) if leg.quantity else 0.0,
                    trade_date=leg.trade_date,
                    currency=leg.currency,
                )
            )
        elif leg.type == SELL:
            remaining = leg.quantity
            sell_fee_per_unit = (leg.fee / leg.quantity) if leg.quantity else 0.0
            while remaining > 1e-9:
                if not open_parcels:
                    raise PortfolioError(
                        f"{ticker}: sell of {leg.quantity} on "
                        f"{leg.trade_date} exceeds units held (oversell)"
                    )
                parcel = open_parcels[0]
                take = min(remaining, parcel.quantity)
                proceeds = take * (leg.price_per_unit - sell_fee_per_unit)
                cost_base = take * (parcel.price_per_unit + parcel.fee_per_unit)
                realised.append(
                    RealisedEvent(
                        ticker=ticker,
                        quantity=take,
                        buy_date=parcel.trade_date,
                        sell_date=leg.trade_date,
                        proceeds=proceeds,
                        cost_base=cost_base,
                        currency=parcel.currency,
                        # Strictly more than 12 calendar months. Compared as
                        # dates, not day counts: 365-day arithmetic flags an
                        # exactly-12-month hold as eligible when the span
                        # crosses 29 February.
                        cgt_discount_eligible=leg.trade_date
                        > _one_year_after(parcel.trade_date),
                    )
                )
                parcel.quantity -= take
                remaining -= take
                if parcel.quantity <= 1e-9:
                    open_parcels.pop(0)
        else:
            raise PortfolioError(f"{ticker}: unknown transaction type '{leg.type}'")

    return realised, [p for p in open_parcels if p.quantity > 1e-9]


# --------------------------------------------------------------------------- #
# Australian financial year helpers
# --------------------------------------------------------------------------- #
def financial_year_of(d: dt.date) -> str:
    """Australian FY label for a date, e.g. 2024-03-01 -> "2023-24"."""
    start = d.year if d.month >= 7 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _financial_year_bounds(fy: str) -> tuple[dt.date, dt.date]:
    """Bounds for an FY label like "2023-24" -> (2023-07-01, 2024-06-30)."""
    try:
        start_year = int(fy.split("-")[0])
    except (ValueError, AttributeError):
        raise PortfolioError(f"invalid financial year '{fy}' (use e.g. 2023-24)")
    return dt.date(start_year, 7, 1), dt.date(start_year + 1, 6, 30)


# --------------------------------------------------------------------------- #
# DB-facing operations
# --------------------------------------------------------------------------- #
def _legs_by_ticker(transactions: list[Transaction]) -> dict[str, list[Leg]]:
    grouped: dict[str, list[Leg]] = {}
    # Insertion (id) order is the FIFO tiebreak for same-day, same-type legs,
    # so don't rely on the caller's (or the database's) row order.
    transactions = sorted(transactions, key=lambda t: (t.trade_date, t.id))
    for t in transactions:
        grouped.setdefault(t.ticker, []).append(
            Leg(
                type=t.type,
                quantity=t.quantity,
                price_per_unit=t.price_per_unit,
                trade_date=t.trade_date,
                fee=t.fee or 0.0,
                currency=t.currency or config.BASE_CURRENCY,
            )
        )
    return grouped


def _actual_transactions(session: Session) -> list[Transaction]:
    return (
        session.query(Transaction)
        .join(Portfolio)
        .filter(Portfolio.type == "actual")
        .order_by(Transaction.trade_date, Transaction.id)
        .all()
    )


def get_transactions(session: Session) -> list[dict]:
    """All transactions across actual portfolios, newest trade first."""
    txns = _actual_transactions(session)
    txns.sort(key=lambda t: (t.trade_date, t.id), reverse=True)
    return [t.to_dict() for t in txns]


def _process_all(
    grouped: dict[str, list[Leg]],
) -> tuple[list[RealisedEvent], dict[str, list[Parcel]], list[str]]:
    """Run FIFO per ticker, isolating failures.

    A data issue on one ticker (e.g. an oversell from incomplete history) is
    captured as a warning rather than aborting the whole portfolio.
    """
    events: list[RealisedEvent] = []
    parcels_by: dict[str, list[Parcel]] = {}
    warnings: list[str] = []
    for ticker, legs in grouped.items():
        try:
            realised, parcels = fifo_process(ticker, legs)
        except PortfolioError as exc:
            warnings.append(str(exc))
            continue
        events.extend(realised)
        if parcels:
            parcels_by[ticker] = parcels
    return events, parcels_by, warnings


def compute_realised(
    session: Session,
    financial_year: str | None = None,
    taxable_income: float | None = None,
) -> dict:
    """Realised gains and a CGT-discount summary across actual portfolios.

    If ``financial_year`` (e.g. "2023-24") is given, only sells settled within
    that Australian FY are included. If ``taxable_income`` is given, an estimate
    of the additional tax the net gain attracts is added (see tax.py).
    """
    grouped = _legs_by_ticker(_actual_transactions(session))
    events, _, warnings = _process_all(grouped)

    if financial_year:
        start, end = _financial_year_bounds(financial_year)
        events = [e for e in events if start <= e.sell_date <= end]

    events.sort(key=lambda e: e.sell_date)

    # Currency-grouped totals (exact, no FX assumptions).
    by_currency: dict[str, dict] = {}
    for e in events:
        ccy = e.currency or config.BASE_CURRENCY
        bucket = by_currency.setdefault(
            ccy, {"proceeds": 0.0, "cost_base": 0.0, "gain": 0.0}
        )
        bucket["proceeds"] += e.proceeds
        bucket["cost_base"] += e.cost_base
        bucket["gain"] += e.gain
    for bucket in by_currency.values():
        for k in bucket:
            bucket[k] = round(bucket[k], 2)

    # Simplified CGT estimate (see module docstring caveats).
    total_gain = sum(e.gain for e in events)
    discountable = sum(e.gain for e in events if e.cgt_discount_eligible and e.gain > 0)
    short_term = sum(e.gain for e in events if not e.cgt_discount_eligible)
    discount = discountable * 0.5
    net_capital_gain = max(total_gain - discount, 0.0) if total_gain > 0 else total_gain

    cgt_estimate = {
        "total_realised_gain": round(total_gain, 2),
        "discount_eligible_gain": round(discountable, 2),
        "short_term_gain": round(short_term, 2),
        "estimated_discount": round(discount, 2),
        "estimated_net_capital_gain": round(net_capital_gain, 2),
        "disclaimer": (
            "Informational estimate only, not tax advice. Assumes single "
            "currency per parcel; ignores capital-loss offset ordering and "
            "carried-forward losses."
        ),
    }
    if taxable_income is not None:
        cgt_estimate["estimated_tax"] = tax.estimate_tax_on_gain(
            taxable_income, net_capital_gain, financial_year
        )

    return {
        "base_currency": config.BASE_CURRENCY,
        "financial_year": financial_year,
        "events": [e.to_dict() for e in events],
        "by_currency": by_currency,
        "cgt_estimate": cgt_estimate,
        "warnings": warnings,
    }


def open_parcels(session: Session) -> dict[str, list[Parcel]]:
    """Current open parcels per ticker, derived from the transaction ledger."""
    grouped = _legs_by_ticker(_actual_transactions(session))
    _, parcels_by, _ = _process_all(grouped)
    return parcels_by


# --------------------------------------------------------------------------- #
# CSV import
# --------------------------------------------------------------------------- #
@dataclass
class ImportResult:
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


# --------------------------------------------------------------------------- #
# CMC "Cash Transaction Summary" import
# --------------------------------------------------------------------------- #
# Trade rows look like:  "Bght 154 VGMF @ 64.6100 17284978"
#                        "Sold 125 VGAD @ 80.0800 AUD 21591579"
#                        "Bght 10 AAPL:US @ 257.4110 AUD 25664103"
# Everything else (deposits, interest, dividends, transfers, balances) is noise.
_CMC_TRADE_RE = re.compile(
    r"^(?P<action>Bght|Sold)\s+"
    r"(?P<qty>[\d,]+(?:\.\d+)?)\s+"
    r"(?P<ticker>[A-Za-z0-9]+)"
    r"(?::(?P<market>US))?\s+@\s+"
    r"(?P<price>[\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_CMC_REF_RE = re.compile(r"(\d+)\s*$")


def _looks_like_cmc(fieldnames: list[str]) -> bool:
    cols = {(f or "").strip().lower() for f in fieldnames}
    return "description" in cols and ("debit $" in cols or "credit $" in cols)


def parse_cmc_description(description: str) -> dict | None:
    """Parse a CMC trade description into transaction fields, or None if the
    row is not a trade (deposit, dividend, interest, transfer, balance, ...)."""
    match = _CMC_TRADE_RE.match(description.strip())
    if not match:
        return None
    ticker = match.group("ticker").upper()
    market = (match.group("market") or "").upper()
    if market == "US":
        exchange = "US"  # priced in USD by yfinance; cost stays AUD
    elif ticker in CBOE_AU_TICKERS:
        exchange = "CBOE_AU"
    else:
        exchange = "ASX"
    ref = _CMC_REF_RE.search(description.strip())
    return {
        "type": BUY if match.group("action").lower() == "bght" else SELL,
        "ticker": ticker,
        "exchange": exchange,
        "quantity": float(match.group("qty").replace(",", "")),
        "price_per_unit": float(match.group("price").replace(",", "")),
        "reference": ref.group(1) if ref else None,
    }


def _cmc_fee(ttype: str, quantity: float, price: float, debit, credit) -> float:
    """Derive brokerage from the cash leg: total consideration − qty × price.

    On the dummy export these columns are blank (fee 0); on the real export the
    Debit/Credit values let us recover the fee automatically.
    """
    consideration = quantity * price
    raw = debit if ttype == BUY else credit
    try:
        value = _parse_float(raw, "amount")  # None if blank
    except PortfolioError:
        # An unparseable cash value (e.g. "$1,234.56 CR") must not abort the
        # whole import — the trade itself is fine, we just can't derive a fee.
        value = None
    if value is None:
        return 0.0
    fee = (value - consideration) if ttype == BUY else (consideration - value)
    return round(fee, 4) if fee > 0 else 0.0


def _ingest_cmc(session, reader, portfolio, replace, result: ImportResult) -> ImportResult:
    """Import a CMC cash-transaction-summary CSV (auto-detected)."""
    if replace:
        portfolio.transactions.clear()
        session.flush()

    for line_no, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): v for k, v in row.items()}
        description = (row.get("description") or "").strip()
        parsed = parse_cmc_description(description)
        if parsed is None:
            result.skipped += 1  # non-trade row (expected, not an error)
            continue
        trade_date = _parse_date(_clean(row.get("date")))
        if trade_date is None:
            result.skipped += 1
            result.errors.append(
                {"row": line_no, "error": f"bad date for '{description[:40]}'"}
            )
            continue
        portfolio.transactions.append(
            Transaction(
                ticker=parsed["ticker"],
                exchange=parsed["exchange"],
                type=parsed["type"],
                quantity=parsed["quantity"],
                price_per_unit=parsed["price_per_unit"],
                fee=_cmc_fee(
                    parsed["type"],
                    parsed["quantity"],
                    parsed["price_per_unit"],
                    row.get("debit $"),
                    row.get("credit $"),
                ),
                currency=None,  # CMC prices are in AUD (the base currency)
                trade_date=trade_date,
                reference=parsed["reference"],
            )
        )
        result.added += 1
    session.flush()
    return result


def ingest_transactions_csv(
    session: Session,
    raw: bytes | str,
    portfolio_name: str | None = None,
    replace: bool = False,
) -> ImportResult:
    """Ingest a transactions CSV into an actual portfolio.

    Two formats are accepted and auto-detected:
      * Native: ticker, type (buy/sell), quantity, price_per_unit, trade_date,
        and optional exchange, fee, currency, reference.
      * CMC "Cash Transaction Summary" export (Date, Description, Debit $,
        Credit $, Balance $) — trade rows are parsed from the Description and
        non-trade rows (deposits, dividends, interest, transfers) are skipped.

    Rows are validated individually; a bad row is recorded and skipped.
    """
    name = portfolio_name or config.DEFAULT_PORTFOLIO
    portfolio = ensure_portfolio(session, name, "actual")
    result = ImportResult(portfolio=name)

    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    reader = csv.DictReader(io.StringIO(text))

    if _looks_like_cmc(reader.fieldnames or []):
        return _ingest_cmc(session, reader, portfolio, replace, result)

    headers = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
    required = {"ticker", "type", "quantity", "price_per_unit", "trade_date"}
    missing = required - headers
    if missing:
        raise PortfolioError(
            f"Transactions CSV is missing column(s): {', '.join(sorted(missing))}"
        )

    if replace:
        portfolio.transactions.clear()
        session.flush()

    for line_no, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): v for k, v in row.items()}
        ticker = _clean(row.get("ticker"))
        ttype = (_clean(row.get("type")) or "").lower()
        if not ticker:
            result.skipped += 1
            result.errors.append({"row": line_no, "error": "missing ticker"})
            continue
        if ttype not in (BUY, SELL):
            result.skipped += 1
            result.errors.append(
                {"row": line_no, "error": f"type must be buy or sell, got '{ttype}'"}
            )
            continue
        try:
            quantity = _parse_float(row.get("quantity"), "quantity", required=True)
            price = _parse_float(row.get("price_per_unit"), "price_per_unit", required=True)
            fee = _parse_float(row.get("fee"), "fee") or 0.0
            trade_date = _parse_date(row.get("trade_date"))
            if trade_date is None:
                raise PortfolioError("missing trade_date")
            if quantity is None or quantity <= 0:
                raise PortfolioError("quantity must be positive")
        except PortfolioError as exc:
            result.skipped += 1
            result.errors.append({"row": line_no, "error": str(exc)})
            continue

        portfolio.transactions.append(
            Transaction(
                ticker=ticker.upper(),
                exchange=(_clean(row.get("exchange")) or DEFAULT_EXCHANGE).upper(),
                type=ttype,
                quantity=quantity,
                price_per_unit=price,
                fee=fee,
                currency=_upper_or_none(row.get("currency")),
                trade_date=trade_date,
                reference=_clean(row.get("reference")),
            )
        )
        result.added += 1

    session.flush()
    return result


# --------------------------------------------------------------------------- #
# Derive holdings from the ledger
# --------------------------------------------------------------------------- #
def sync_holdings_from_transactions(
    session: Session, portfolio_name: str | None = None
) -> dict:
    """Replace a portfolio's holdings with the open parcels from its ledger.

    Each open parcel becomes one holding row (preserving its acquisition date
    and per-parcel cost base), so the existing valuation/summary/comparison
    views reflect the transaction ledger.
    """
    name = portfolio_name or config.DEFAULT_PORTFOLIO
    portfolio = ensure_portfolio(session, name, "actual")

    grouped = _legs_by_ticker(portfolio.transactions)
    # Remember a representative exchange per ticker for the holding row.
    meta = {t.ticker: t for t in portfolio.transactions}

    _, parcels_by, warnings = _process_all(grouped)

    new_holdings: list[Holding] = []
    for ticker, parcels in parcels_by.items():
        template = meta[ticker]
        for parcel in parcels:
            new_holdings.append(
                Holding(
                    ticker=ticker,
                    exchange=template.exchange,
                    quantity=parcel.quantity,
                    cost_base_per_unit=parcel.price_per_unit + parcel.fee_per_unit,
                    cost_currency=parcel.currency,
                    date_acquired=parcel.trade_date,
                    broker=None,
                    asset_class="stock",
                )
            )

    portfolio.holdings = new_holdings
    session.flush()
    return {
        "portfolio": name,
        "holdings_created": len(new_holdings),
        "tickers": sorted(parcels_by.keys()),
        "warnings": warnings,
    }
