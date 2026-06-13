"""Actual performance over time: daily valuation, TWR, XIRR, benchmarks."""
import datetime as dt

import pandas as pd
import pytest

import performance
import portfolio as pf


def history_frame(closes: dict[str, float], dividends: dict[str, float] | None = None):
    """Build a daily-history DataFrame in the shape _fetch_daily_history returns."""
    idx = pd.to_datetime(list(closes))
    frame = pd.DataFrame({"close": list(closes.values())}, index=idx)
    frame["dividends"] = 0.0
    for date, amount in (dividends or {}).items():
        frame.loc[pd.Timestamp(date), "dividends"] = amount
    return frame.sort_index()


# --------------------------------------------------------------------------- #
# XIRR
# --------------------------------------------------------------------------- #
def test_xirr_simple_one_year_gain():
    flows = [(dt.date(2023, 1, 1), -1000.0), (dt.date(2024, 1, 1), 1100.0)]
    assert performance.xirr(flows) == pytest.approx(0.10, abs=0.001)

def test_xirr_requires_both_signs():
    assert performance.xirr([(dt.date(2023, 1, 1), -1000.0)]) is None
    assert performance.xirr(
        [(dt.date(2023, 1, 1), 1000.0), (dt.date(2024, 1, 1), 1100.0)]
    ) is None

def test_xirr_with_interim_contribution():
    # -1000 at t0, -1000 after 1y, +2200 after 2y: r such that
    # 1000(1+r)^2 + 1000(1+r) = 2200 -> r ~ 6.45%
    flows = [
        (dt.date(2022, 1, 1), -1000.0),
        (dt.date(2023, 1, 1), -1000.0),
        (dt.date(2024, 1, 1), 2200.0),
    ]
    assert performance.xirr(flows) == pytest.approx(0.0645, abs=0.002)


# --------------------------------------------------------------------------- #
# TWR fundamentals
# --------------------------------------------------------------------------- #
def test_price_doubles_twr_100pct(session, add_transaction, daily_history):
    daily_history["AOV.AX"] = history_frame(
        {"2023-01-01": 2.0, "2023-06-01": 4.0}
    )
    add_transaction("AOV", "buy", 100, 2.0, "2023-01-01")
    out = performance.compute_performance(session, "max")
    assert out["available"] is True
    assert out["twr_pct"] == pytest.approx(100.0, abs=0.1)
    assert out["current_value"] == pytest.approx(400.0)
    assert out["estimated_tickers"] == []

def test_buying_more_is_not_performance(session, add_transaction, daily_history):
    # Price never moves; a second buy must not register as a gain.
    daily_history["AOV.AX"] = history_frame(
        {"2023-01-01": 2.0, "2023-03-01": 2.0, "2023-06-01": 2.0}
    )
    add_transaction("AOV", "buy", 100, 2.0, "2023-01-01")
    add_transaction("AOV", "buy", 300, 2.0, "2023-03-01")
    out = performance.compute_performance(session, "max")
    assert out["twr_pct"] == pytest.approx(0.0, abs=0.01)
    assert out["net_invested"] == pytest.approx(800.0)
    assert out["current_value"] == pytest.approx(800.0)

def test_twr_ignores_flow_timing_but_xirr_reflects_it(
    session, add_transaction, daily_history
):
    # +100% in the first leg, flat in the second. A big buy at the top makes
    # the money-weighted return much lower than the time-weighted one.
    daily_history["AOV.AX"] = history_frame(
        {"2023-01-01": 1.0, "2023-06-01": 2.0, "2024-01-01": 2.0}
    )
    add_transaction("AOV", "buy", 100, 1.0, "2023-01-01")
    add_transaction("AOV", "buy", 1000, 2.0, "2023-06-01")
    out = performance.compute_performance(session, "max")
    assert out["twr_pct"] == pytest.approx(100.0, abs=0.1)
    assert out["money_weighted_pct"] is not None
    assert out["money_weighted_pct"] < 20.0  # most dollars earned nothing

def test_selling_is_an_outflow_not_a_loss(session, add_transaction, daily_history):
    daily_history["AOV.AX"] = history_frame(
        {"2023-01-01": 2.0, "2023-06-01": 4.0, "2024-01-01": 4.0}
    )
    add_transaction("AOV", "buy", 100, 2.0, "2023-01-01")
    add_transaction("AOV", "sell", 50, 4.0, "2023-06-01")
    out = performance.compute_performance(session, "max")
    assert out["twr_pct"] == pytest.approx(100.0, abs=0.1)
    assert out["current_value"] == pytest.approx(200.0)  # 50 units left @ 4
    assert out["net_invested"] == pytest.approx(0.0)  # 200 in, 200 out

def test_dividends_count_as_income(session, add_transaction, daily_history):
    # Flat price, a 5% dividend: TWR should be ~5% and income reported.
    daily_history["AOV.AX"] = history_frame(
        {"2023-01-01": 2.0, "2023-06-01": 2.0, "2024-01-01": 2.0},
        dividends={"2023-06-01": 0.10},
    )
    add_transaction("AOV", "buy", 100, 2.0, "2023-01-01")
    out = performance.compute_performance(session, "max")
    assert out["income_received"] == pytest.approx(10.0)
    assert out["twr_pct"] == pytest.approx(5.0, abs=0.1)

def test_fees_reduce_performance(session, add_transaction, daily_history):
    daily_history["AOV.AX"] = history_frame(
        {"2023-01-01": 2.0, "2023-06-01": 2.0}
    )
    add_transaction("AOV", "buy", 100, 2.0, "2023-01-01", fee=10.0)
    out = performance.compute_performance(session, "max")
    # Invested 210 (incl. fee), worth 200 -> ~-4.8%.
    assert out["twr_pct"] == pytest.approx(-4.76, abs=0.1)


# --------------------------------------------------------------------------- #
# FX and estimated (delisted) tickers
# --------------------------------------------------------------------------- #
def test_fx_move_included_in_base_performance(session, add_transaction, daily_history):
    # USD price flat; AUD/USD up 10% -> +10% in AUD terms.
    daily_history["AAPL"] = history_frame(
        {"2023-01-01": 100.0, "2023-06-01": 100.0}
    )
    daily_history["USDAUD=X"] = history_frame(
        {"2023-01-01": 1.40, "2023-06-01": 1.54}
    )
    add_transaction("AAPL", "buy", 10, 100.0, "2023-01-01", exchange="US",
                    currency="USD")
    out = performance.compute_performance(session, "max")
    assert out["twr_pct"] == pytest.approx(10.0, abs=0.1)
    assert out["current_value"] == pytest.approx(1540.0)

def test_delisted_ticker_valued_at_trade_prices(
    session, add_transaction, daily_history
):
    # VGMF has no Yahoo history: its value is interpolated between its own
    # trade prices and the ticker is flagged. Sold at a gain -> gain is real.
    add_transaction("VGMF", "buy", 100, 2.0, "2023-01-01")
    add_transaction("VGMF", "sell", 100, 3.0, "2023-06-01")
    out = performance.compute_performance(session, "max")
    assert out["estimated_tickers"] == ["VGMF"]
    assert any("VGMF" in w for w in out["warnings"])
    assert out["twr_pct"] == pytest.approx(50.0, abs=0.1)
    assert out["current_value"] == pytest.approx(0.0)

def test_delisted_ticker_loss_has_no_single_day_cliff(
    session, add_transaction, daily_history
):
    # The VGMF case from the real ledger: bought high, sold ~19% lower seven
    # months later, with no interim prices. The loss is real and must show in
    # the cumulative TWR, but it should be spread across the holding period —
    # no single day should carry the whole drop.
    add_transaction("VGMF", "buy", 154, 64.61, "2022-01-10")
    add_transaction("VGMF", "sell", 154, 52.376, "2022-07-13")
    out = performance.compute_performance(session, "max")
    # Cumulative loss is correct (52.376/64.61 - 1).
    assert out["twr_pct"] == pytest.approx(-18.9, abs=0.3)
    # No day in the indexed series drops more than ~3% (interpolated glide),
    # versus a single ~-19% cliff under the old carry-forward valuation.
    idx = [p["portfolio"] for p in out["series"] if p["portfolio"] is not None]
    worst = min(b / a - 1.0 for a, b in zip(idx, idx[1:]))
    assert worst > -0.05


# --------------------------------------------------------------------------- #
# Windowing and benchmarks
# --------------------------------------------------------------------------- #
def test_period_window_rebases(session, add_transaction, daily_history):
    # +100% in an early year, flat since: "1y" should show ~0%, "max" ~100%.
    today = dt.date.today()
    daily_history["AOV.AX"] = history_frame(
        {
            "2020-01-01": 1.0,
            "2021-01-01": 2.0,
            today.isoformat(): 2.0,
        }
    )
    add_transaction("AOV", "buy", 100, 1.0, "2020-01-01")
    out_max = performance.compute_performance(session, "max")
    out_1y = performance.compute_performance(session, "1y")
    assert out_max["twr_pct"] == pytest.approx(100.0, abs=0.5)
    assert out_1y["twr_pct"] == pytest.approx(0.0, abs=0.5)
    assert out_max["twr_annualised_pct"] is not None
    assert out_1y["start_date"] > out_max["start_date"]

def test_benchmark_overlay_rebased_to_window(
    session, add_transaction, daily_history
):
    daily_history["AOV.AX"] = history_frame(
        {"2023-01-01": 1.0, "2024-01-01": 1.0}
    )
    daily_history["VAS.AX"] = history_frame(
        {"2023-01-01": 100.0, "2024-01-01": 110.0}
    )
    add_transaction("AOV", "buy", 100, 1.0, "2023-01-01")
    pf.create_benchmark_from_dict(
        session, {"name": "ASX", "constituents": [{"ticker": "VAS", "weight_pct": 100}]}
    )
    out = performance.compute_performance(session, "max")
    assert out["benchmarks"][0]["name"] == "ASX"
    assert out["benchmarks"][0]["return_pct"] == pytest.approx(10.0, abs=0.1)
    last_point = out["series"][-1]
    assert last_point["ASX"] == pytest.approx(110.0, abs=0.5)
    assert last_point["portfolio"] == pytest.approx(100.0, abs=0.5)

def test_series_downsampled(session, add_transaction, daily_history):
    daily_history["AOV.AX"] = history_frame(
        {"2020-01-01": 1.0, "2026-01-01": 2.0}
    )
    add_transaction("AOV", "buy", 100, 1.0, "2020-01-01")
    out = performance.compute_performance(session, "max")
    assert len(out["series"]) <= performance.MAX_CHART_POINTS + 1
    assert out["series"][-1]["date"] == out["end_date"]


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
def test_endpoint_no_transactions(client):
    body = client.get("/portfolio/performance").get_json()
    assert body["available"] is False
    assert "Transactions" in body["reason"]

def test_endpoint_rejects_bad_period(client):
    resp = client.get("/portfolio/performance?period=bogus")
    assert resp.status_code == 400

def test_endpoint_returns_series(client, session, add_transaction, daily_history):
    daily_history["AOV.AX"] = history_frame(
        {"2023-01-01": 2.0, "2023-06-01": 4.0}
    )
    add_transaction("AOV", "buy", 100, 2.0, "2023-01-01")
    resp = client.get("/portfolio/performance?period=max")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["available"] is True
    assert body["twr_pct"] == pytest.approx(100.0, abs=0.1)
    assert body["series"][0]["portfolio"] == pytest.approx(100.0)
