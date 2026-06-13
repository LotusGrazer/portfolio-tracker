"""Actual portfolio performance over time, derived from the transaction ledger.

Unlike the benchmark comparison (portfolio.py), which asks "how would my
*current* allocation have performed?", this module reconstructs what the
portfolio actually held on every day since the first recorded trade and
computes:

  * a daily market-value series (unadjusted closes, FX-converted to base);
  * a **time-weighted return** (TWR) index — daily returns with external cash
    flows stripped out, compounded — the number comparable to a benchmark;
  * a **money-weighted return** (XIRR) — the rate the invested dollars
    actually earned, where contribution timing does matter;
  * benchmark total-return indices over the same window, for overlay.

Conventions / scope:
  * The portfolio is securities-only: every buy is an external inflow (cost +
    fee) and every sell an external outflow (proceeds − fee). Cash balances
    are not modelled.
  * Daily returns treat flows as end-of-day —
    r_t = (V_t + divs_t + sells_t − buys_t) / V_{t-1} − 1 — so a same-day
    price move isn't diluted into money that arrived that day. When the day
    starts from zero (the first buy, or re-entering after a full exit) the
    buy is the day's opening capital instead: r_t = (V_t + …) / buys_t − 1.
  * Dividends are credited as income on their ex-date (per-share dividend ×
    units held the previous day) and assumed withdrawn, not reinvested —
    reinvestment shows up as the explicit buy it actually was. Benchmarks are
    accumulation series (dividends reinvested), so a portfolio that lets cash
    sit idle shows the real drag of doing so.
  * Valuation uses **unadjusted** closes: adjusted ("accumulation") prices
    rescale history, which mis-values positions when quantities change.
  * Tickers with no usable price history (e.g. delisted funds) are valued by
    linearly interpolating between their own trade prices, and reported in
    ``estimated_tickers``. The endpoints are real trades so the cumulative
    return is exact; interpolating (rather than holding the last price flat)
    just avoids dumping a whole holding period's price move onto the single
    day a trade reveals the new price. Days before a ticker's history begins
    are anchored the same way.
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

import config
from ledger import BUY
from models import Portfolio, Transaction
from portfolio import SUPPORTED_PERIODS, resolve_symbol

# Cap the number of points returned for charting; long windows are
# downsampled (keeping the final point) so the frontend stays snappy.
MAX_CHART_POINTS = 366

_MIN_ANNUALISE_YEARS = 0.97  # same convention as portfolio.py


# --------------------------------------------------------------------------- #
# Historical data (single network seam, mocked in tests)
# --------------------------------------------------------------------------- #
def _fetch_daily_history(symbol: str) -> pd.DataFrame | None:
    """Full daily history for ``symbol``: unadjusted ``close`` + ``dividends``.

    Returns None when no usable history exists (unknown/delisted symbols).
    """
    try:
        hist = yf.Ticker(symbol).history(period="max", auto_adjust=False)
    except Exception:
        return None
    if hist is None or hist.empty or "Close" not in hist:
        return None
    out = pd.DataFrame({"close": hist["Close"]})
    out["dividends"] = (
        hist["Dividends"] if "Dividends" in hist else 0.0
    )
    out = out.dropna(subset=["close"])
    if out.empty:
        return None
    # Normalise to naive midnight dates so series from different exchanges
    # (and trade dates) align on calendar days.
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    return out[~out.index.duplicated(keep="last")]


def _prefetch_histories(symbols: set[str]) -> dict[str, pd.DataFrame | None]:
    """Fetch full histories for many symbols concurrently."""
    out: dict[str, pd.DataFrame | None] = {}
    if not symbols:
        return out
    with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as pool:
        futures = {pool.submit(_fetch_daily_history, s): s for s in symbols}
        for future in as_completed(futures):
            try:
                out[futures[future]] = future.result()
            except Exception:
                out[futures[future]] = None
    return out


# --------------------------------------------------------------------------- #
# Money-weighted return (XIRR)
# --------------------------------------------------------------------------- #
def xirr(flows: list[tuple[dt.date, float]]) -> float | None:
    """Annualised internal rate of return for dated cash flows.

    Sign convention: investments negative, proceeds/terminal value positive.
    Returns None when no rate can be solved (e.g. flows all one sign).
    """
    flows = sorted((d, f) for d, f in flows if f != 0.0)
    if len(flows) < 2:
        return None
    if all(f > 0 for _, f in flows) or all(f < 0 for _, f in flows):
        return None
    t0 = flows[0][0]

    def npv(rate: float) -> float:
        return sum(
            f / (1.0 + rate) ** ((d - t0).days / 365.25) for d, f in flows
        )

    lo, hi = -0.9999, 100.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-9:
            break
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


# --------------------------------------------------------------------------- #
# Series construction helpers
# --------------------------------------------------------------------------- #
def _units_series(legs: list[Transaction], index: pd.DatetimeIndex) -> pd.Series:
    """Cumulative units held per day (trades take effect end of trade date)."""
    deltas: dict[pd.Timestamp, float] = {}
    for t in legs:
        ts = pd.Timestamp(t.trade_date)
        signed = t.quantity if t.type == BUY else -t.quantity
        deltas[ts] = deltas.get(ts, 0.0) + signed
    return (
        pd.Series(deltas)
        .reindex(index, fill_value=0.0)
        .cumsum()
        .clip(lower=0.0)  # an oversold ledger gap can't yield negative units
    )


def _price_series(
    legs: list[Transaction],
    history: pd.DataFrame | None,
    index: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series | None, bool]:
    """Daily ``(close, dividends, estimated)`` for one ticker.

    Without history (delisted tickers), the price is linearly interpolated
    between the ticker's own trade prices: the endpoints are real, so the
    cumulative return is exact, but the known move is spread smoothly over the
    holding period instead of cliff-stepping onto the single day a trade
    reveals the new price (which would show as a spurious one-day jump). The
    same anchoring fills any window before real history begins. ``estimated``
    reports whether trade-price anchoring was needed.
    """
    trade_prices = pd.Series(
        {pd.Timestamp(t.trade_date): t.price_per_unit for t in legs}
    ).sort_index()

    if history is None:
        return _interpolate_anchors(trade_prices, index), None, True

    closes = history["close"]
    estimated = False
    early = trade_prices[trade_prices.index < closes.index[0]]
    if len(early):
        # Glide from the pre-history trade anchors into the first real close
        # rather than holding flat and jumping.
        closes = _interpolate_anchors(pd.concat([early, closes]), index)
        estimated = True
    else:
        closes = closes.reindex(index, method="ffill")
    dividends = history["dividends"].reindex(index, fill_value=0.0)
    return closes, dividends, estimated


def _interpolate_anchors(anchors: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Reindex ``anchors`` to ``index``, interpolating gaps by date.

    Time-interpolation distributes a known price move smoothly between anchor
    dates; the last value is carried forward past the final anchor. Leading
    days before the first anchor stay NaN (the ticker isn't held yet, so its
    weight is zero and the caller's outer ``fillna(0)`` covers it).
    """
    deduped = anchors[~anchors.index.duplicated(keep="last")]
    return deduped.reindex(index).interpolate(method="time").ffill()


def _fx_series(
    currency: str | None,
    base: str,
    histories: dict[str, pd.DataFrame | None],
    index: pd.DatetimeIndex,
) -> pd.Series:
    """Daily units-of-base per unit of ``currency`` (1.0 for the base itself)."""
    if not currency or currency == base:
        return pd.Series(1.0, index=index)
    history = histories.get(f"{currency}{base}=X")
    if history is None:
        return pd.Series(1.0, index=index)  # degrade to native rather than fail
    return history["close"].reindex(index, method="ffill").bfill()


def _window_start(period: str, end: pd.Timestamp) -> pd.Timestamp | None:
    """Start date implied by a period label, or None for 'max'."""
    offsets = {
        "1mo": pd.DateOffset(months=1),
        "3mo": pd.DateOffset(months=3),
        "6mo": pd.DateOffset(months=6),
        "1y": pd.DateOffset(years=1),
        "2y": pd.DateOffset(years=2),
        "3y": pd.DateOffset(years=3),
        "5y": pd.DateOffset(years=5),
        "10y": pd.DateOffset(years=10),
    }
    if period == "max":
        return None
    if period == "ytd":
        return pd.Timestamp(end.year, 1, 1)
    return end - offsets[period]


def _downsample(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Thin a daily index to at most MAX_CHART_POINTS, keeping the last day."""
    if len(index) <= MAX_CHART_POINTS:
        return index
    step = -(-len(index) // MAX_CHART_POINTS)  # ceil
    keep = index[::step]
    if keep[-1] != index[-1]:
        keep = keep.append(index[-1:])
    return keep


def _benchmark_index(
    benchmark: Portfolio,
    base: str,
    histories: dict[str, pd.DataFrame | None],
    index: pd.DatetimeIndex,
) -> pd.Series | None:
    """Daily total-return index of a benchmark in ``base``, weighted.

    Each constituent's total-return factor is (close + dividend) / previous
    close — i.e. dividends reinvested — FX-converted daily. Constituents
    without data are dropped and the remaining weights renormalised.
    """
    indices: list[tuple[float, pd.Series]] = []
    for c in benchmark.holdings:
        symbol, currency = resolve_symbol(c.ticker, c.exchange)
        history = histories.get(symbol)
        if history is None or c.weight_pct in (None, 0):
            continue
        fx = _fx_series(currency, base, histories, index)
        close = history["close"].reindex(index, method="ffill") * fx
        div = history["dividends"].reindex(index, fill_value=0.0) * fx
        prev = close.shift(1)
        factor = ((close + div) / prev).where(prev > 0, 1.0).fillna(1.0)
        indices.append((c.weight_pct, factor.cumprod()))
    if not indices:
        return None
    total_weight = sum(w for w, _ in indices)
    blended = sum((w / total_weight) * s for w, s in indices)
    return blended


def _rebase(series: pd.Series) -> pd.Series | None:
    """Index a series to 100 at its first valid, non-zero point."""
    series = series.dropna()
    series = series[series > 0]
    if series.empty:
        return None
    return series / series.iloc[0] * 100.0


# --------------------------------------------------------------------------- #
# Risk / risk-adjusted metrics (computed on the daily series above)
# --------------------------------------------------------------------------- #
TRADING_DAYS = 252
MIN_METRIC_OBS = 20  # below this, daily-frequency statistics are just noise


def _pct(value: float | None) -> float | None:
    """Fraction -> rounded percent, passing None through."""
    return round(value * 100.0, 2) if value is not None else None


def _business_day_returns(level: pd.Series) -> pd.Series:
    """Daily returns of an indexed level series, restricted to weekdays.

    The daily index includes weekends (flat, so ~0 returns) which would bias
    volatility downward; restricting to Mon–Fri uses the conventional ~252
    trading-day basis and treats Fri→Mon as one step. (Public holidays remain
    as near-zero days — a minor second-order effect.)
    """
    weekday = level[level.index.dayofweek < 5]
    return weekday.pct_change().dropna()


def _annualised_vol(returns: pd.Series) -> float | None:
    if len(returns) < MIN_METRIC_OBS:
        return None
    return float(returns.std(ddof=1) * (TRADING_DAYS ** 0.5))


def _max_drawdown(level: pd.Series) -> float | None:
    """Largest peak-to-trough fall of an indexed level series (negative)."""
    lvl = level.dropna()
    if len(lvl) < 2:
        return None
    return float((lvl / lvl.cummax() - 1.0).min())


def _sharpe(ann_return: float | None, ann_vol: float | None, rf: float) -> float | None:
    if ann_return is None or not ann_vol:
        return None
    return round((ann_return - rf) / ann_vol, 2)


def _beta_correlation(
    port: pd.Series, bench: pd.Series
) -> tuple[float | None, float | None]:
    """Beta and correlation of portfolio daily returns against a benchmark's."""
    df = pd.concat([port, bench], axis=1, join="inner").dropna()
    if len(df) < MIN_METRIC_OBS:
        return None, None
    p, b = df.iloc[:, 0], df.iloc[:, 1]
    var_b, var_p = b.var(ddof=1), p.var(ddof=1)
    beta = round(float(p.cov(b) / var_b), 2) if var_b else None
    # Correlation is undefined if either side is constant (zero variance).
    corr = round(float(p.corr(b)), 2) if (var_b and var_p) else None
    return beta, corr


def _tracking_error(port: pd.Series, bench: pd.Series) -> float | None:
    """Annualised standard deviation of the active (port − bench) daily return."""
    df = pd.concat([port, bench], axis=1, join="inner").dropna()
    if len(df) < MIN_METRIC_OBS:
        return None
    active = df.iloc[:, 0] - df.iloc[:, 1]
    return float(active.std(ddof=1) * (TRADING_DAYS ** 0.5))


def _risk_metrics(
    twr_w: pd.Series,
    twr_annualised: float | None,
    bench_series: dict[str, pd.Series],
    bench_ann_return: dict[str, float | None],
    bench_ids: dict[str, int],
    annualisable: bool,
) -> dict:
    """Risk and risk-adjusted metrics from the windowed daily index series.

    Standalone metrics (volatility, max drawdown, Sharpe) are reported for the
    portfolio and each benchmark; relational metrics (beta, correlation,
    tracking error, information ratio, alpha) describe the **portfolio against
    that benchmark**. Sharpe / IR / alpha are annual-rate concepts, so they
    are only filled for windows of about a year or more (``annualisable``);
    beta, correlation, volatility and drawdown apply to any window with enough
    observations.
    """
    rf = config.RISK_FREE_RATE
    port_returns = _business_day_returns(twr_w)
    port_vol = _annualised_vol(port_returns)

    bench_metrics = []
    for name, series in bench_series.items():
        bench_returns = _business_day_returns(series)
        b_vol = _annualised_vol(bench_returns)
        b_ann = bench_ann_return.get(name)
        beta, corr = _beta_correlation(port_returns, bench_returns)
        te = _tracking_error(port_returns, bench_returns)

        info_ratio = None
        if annualisable and te and twr_annualised is not None and b_ann is not None:
            info_ratio = round((twr_annualised - b_ann) / te, 2)
        alpha = None
        if (
            annualisable
            and beta is not None
            and twr_annualised is not None
            and b_ann is not None
        ):
            alpha = twr_annualised - (rf + beta * (b_ann - rf))

        bench_metrics.append(
            {
                "id": bench_ids.get(name),
                "name": name,
                "annualised_volatility_pct": _pct(b_vol),
                "max_drawdown_pct": _pct(_max_drawdown(series)),
                "sharpe_ratio": _sharpe(b_ann, b_vol, rf),
                "beta": beta,
                "correlation": corr,
                "tracking_error_pct": _pct(te),
                "information_ratio": info_ratio,
                "alpha_pct": _pct(alpha),
            }
        )

    return {
        "risk_free_rate_pct": round(rf * 100.0, 2),
        "trading_days_basis": TRADING_DAYS,
        "observations": len(port_returns),
        # IR / Sharpe / alpha need a year-plus window to be meaningful.
        "annualised_ratios": annualisable,
        "portfolio": {
            "annualised_volatility_pct": _pct(port_vol),
            "max_drawdown_pct": _pct(_max_drawdown(twr_w)),
            "sharpe_ratio": _sharpe(twr_annualised, port_vol, rf),
        },
        "benchmarks": bench_metrics,
    }


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def compute_performance(session: Session, period: str = "max") -> dict:
    """Actual performance of the ledger-backed portfolio over ``period``."""
    base = config.BASE_CURRENCY
    txns = (
        session.query(Transaction)
        .join(Portfolio)
        .filter(Portfolio.type == "actual")
        .order_by(Transaction.trade_date, Transaction.id)
        .all()
    )
    if not txns:
        return {
            "available": False,
            "reason": (
                "No transactions recorded. Actual performance is reconstructed "
                "from the ledger — import your trade history under the "
                "Transactions tab first."
            ),
        }

    # Resolve symbols and the FX pairs needed — for the ledger's tickers and
    # for every benchmark constituent — then fetch all history at once.
    by_ticker: dict[str, list[Transaction]] = {}
    for t in txns:
        by_ticker.setdefault(t.ticker, []).append(t)
    meta = {t.ticker: t for t in txns}  # latest txn wins for exchange

    benchmarks = (
        session.query(Portfolio).filter(Portfolio.type == "benchmark").all()
    )

    symbols: dict[str, tuple[str, str | None]] = {}
    wanted: set[str] = set()
    for ticker, template in meta.items():
        symbol, currency = resolve_symbol(ticker, template.exchange)
        symbols[ticker] = (symbol, currency)
        wanted.add(symbol)
        if currency and currency != base:
            wanted.add(f"{currency}{base}=X")
    for t in txns:
        ccy = t.currency or base
        if ccy != base:
            wanted.add(f"{ccy}{base}=X")
    for bench in benchmarks:
        for c in bench.holdings:
            symbol, currency = resolve_symbol(c.ticker, c.exchange)
            wanted.add(symbol)
            if currency and currency != base:
                wanted.add(f"{currency}{base}=X")
    histories = _prefetch_histories(wanted)

    first_trade = pd.Timestamp(txns[0].trade_date)
    last_close = max(
        (h.index[-1] for h in histories.values() if h is not None),
        default=first_trade,
    )
    end = max(first_trade, last_close, pd.Timestamp(dt.date.today()))
    index = pd.date_range(first_trade, end, freq="D")

    # Daily portfolio value and dividend income, summed across tickers.
    total_value = pd.Series(0.0, index=index)
    income = pd.Series(0.0, index=index)
    estimated: list[str] = []
    for ticker, legs in by_ticker.items():
        symbol, currency = symbols[ticker]
        units = _units_series(legs, index)
        price, dividends, was_estimated = _price_series(
            legs, histories.get(symbol), index
        )
        if was_estimated:
            estimated.append(ticker)
        fx = _fx_series(currency, base, histories, index)
        total_value += (units * price * fx).fillna(0.0)
        if dividends is not None:
            held = units.shift(1, fill_value=0.0)  # entitlement: held before ex-date
            income += (dividends * held * fx).fillna(0.0)

    # External flows per day, in base currency (trade-date FX).
    buys = pd.Series(0.0, index=index)
    sells = pd.Series(0.0, index=index)
    for t in txns:
        ts = pd.Timestamp(t.trade_date)
        fx = _fx_series(t.currency, base, histories, index)
        rate = float(fx.asof(ts)) if ts in index else 1.0
        gross = t.quantity * t.price_per_unit * rate
        fee = (t.fee or 0.0) * rate
        if t.type == BUY:
            buys[ts] += gross + fee
        else:
            sells[ts] += gross - fee

    # Daily TWR linking (see module docstring for the flow convention).
    prev_value = total_value.shift(1, fill_value=0.0)
    starting_fresh = prev_value <= 0
    denominator = prev_value.where(~starting_fresh, buys)
    numerator = total_value + income + sells - buys.where(~starting_fresh, 0.0)
    daily_return = (numerator / denominator - 1.0).where(denominator > 0, 0.0)
    twr_full = (1.0 + daily_return).cumprod()

    # Window the series by the requested period (clamped to the ledger).
    start = _window_start(period, index[-1])
    window = index if start is None else index[index >= start]
    if len(window) < 2:
        window = index[-2:]
    actual_start = window[0]
    full_window = window[0] == index[0]

    value_w = total_value.reindex(window)
    # Sub-windows rebase at the window's first day (whose own return belongs
    # to the prior period); the full history rebases against 1.0 so the very
    # first day's return — where fees bite — still counts.
    twr_base = 1.0 if full_window else float(twr_full.reindex(window).iloc[0])
    twr_w = twr_full.reindex(window) / twr_base * 100.0
    years = (window[-1] - window[0]).days / 365.25
    twr_return = twr_w.iloc[-1] / 100.0 - 1.0
    twr_annualised = (
        (1.0 + twr_return) ** (1.0 / years) - 1.0
        if years >= _MIN_ANNUALISE_YEARS
        else None
    )

    # Money-weighted return over the window. For a sub-window, the opening
    # value stands in as the initial investment and the first day's flows are
    # already inside it; for the full history, the raw flows tell the story.
    flows: list[tuple[dt.date, float]] = []
    if not full_window and value_w.iloc[0] > 0:
        flows.append((window[0].date(), -float(value_w.iloc[0])))
    for ts in window:
        if not full_window and ts == window[0]:
            continue
        day_flow = (
            -float(buys.get(ts, 0.0))
            + float(sells.get(ts, 0.0))
            + float(income.get(ts, 0.0))
        )
        if day_flow:
            flows.append((ts.date(), day_flow))
    if value_w.iloc[-1] > 0:
        flows.append((window[-1].date(), float(value_w.iloc[-1])))
    money_weighted = xirr(flows)

    # Benchmarks over the same window, rebased to 100 at the window start.
    annualisable = years >= _MIN_ANNUALISE_YEARS
    bench_series: dict[str, pd.Series] = {}
    bench_ann_return: dict[str, float | None] = {}  # name -> CAGR (fraction)
    bench_summary = []
    for bench in benchmarks:
        full = _benchmark_index(bench, base, histories, index)
        if full is None:
            continue
        rebased = _rebase(full.reindex(window))
        if rebased is None:
            continue
        bench_series[bench.name] = rebased
        b_return = rebased.iloc[-1] / 100.0 - 1.0
        ann = (
            (1.0 + b_return) ** (1.0 / years) - 1.0 if annualisable else None
        )
        bench_ann_return[bench.name] = ann
        bench_summary.append(
            {
                "id": bench.id,
                "name": bench.name,
                "return_pct": round(b_return * 100.0, 2),
                "annualised_return_pct": _pct(ann),
            }
        )

    metrics = _risk_metrics(
        twr_w,
        twr_annualised,
        bench_series,
        bench_ann_return,
        {b["name"]: b["id"] for b in bench_summary},
        annualisable,
    )

    chart_index = _downsample(window)
    series = []
    for ts in chart_index:
        point: dict = {
            "date": ts.date().isoformat(),
            "value": round(float(value_w.get(ts, 0.0)), 2),
            "portfolio": round(float(twr_w.get(ts)), 2)
            if pd.notna(twr_w.get(ts))
            else None,
        }
        for name, s in bench_series.items():
            v = s.get(ts)
            point[name] = round(float(v), 2) if v is not None and pd.notna(v) else None
        series.append(point)

    net_invested = float(buys.reindex(window).sum() - sells.reindex(window).sum())
    warnings: list[str] = []
    if estimated:
        warnings.append(
            "No usable price history for: "
            + ", ".join(sorted(estimated))
            + ". Their daily values are interpolated between your own trade "
            "prices, so movements between trades aren't captured and volatility "
            "over those periods is understated."
        )

    return {
        "available": True,
        "base_currency": base,
        "period": period,
        "start_date": actual_start.date().isoformat(),
        "end_date": window[-1].date().isoformat(),
        "current_value": round(float(value_w.iloc[-1]), 2),
        "net_invested": round(net_invested, 2),
        "income_received": round(float(income.reindex(window).sum()), 2),
        "twr_pct": round(twr_return * 100.0, 2),
        "twr_annualised_pct": round(twr_annualised * 100.0, 2)
        if twr_annualised is not None
        else None,
        "money_weighted_pct": round(money_weighted * 100.0, 2)
        if money_weighted is not None
        else None,
        "benchmarks": bench_summary,
        "metrics": metrics,
        "series": series,
        "estimated_tickers": sorted(estimated),
        "warnings": warnings,
    }
