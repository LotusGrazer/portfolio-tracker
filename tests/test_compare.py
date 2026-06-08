"""Benchmark-vs-actual comparison: period returns, FX, weighting, endpoint."""
import pandas as pd
import pytest

import portfolio as pf


@pytest.fixture
def history(monkeypatch):
    """Mock the historical-data seam with deterministic close series.

    Populate the returned dict with ``{symbol: [close, ...]}``; unknown symbols
    return no history.
    """
    data: dict[str, list[float]] = {}

    def fake_fetch(symbol, period):  # noqa: ARG001 - period irrelevant to fake
        values = data.get(symbol)
        return pd.Series(values) if values else None

    monkeypatch.setattr(pf, "_fetch_close_series", fake_fetch)
    return data


# --------------------------------------------------------------------------- #
# Period return
# --------------------------------------------------------------------------- #
def test_period_return_native_currency(history):
    history["VAS.AX"] = [100.0, 110.0]
    assert pf._period_return("VAS.AX", "AUD", "3mo", "AUD") == pytest.approx(0.10)


def test_period_return_includes_fx_move(history):
    # Price flat in USD, but AUD/USD moved +10% -> +10% in AUD terms.
    history["AAPL"] = [100.0, 100.0]
    history["USDAUD=X"] = [1.40, 1.54]
    assert pf._period_return("AAPL", "USD", "3mo", "AUD") == pytest.approx(0.10)


def test_period_return_compounds_price_and_fx(history):
    history["AAPL"] = [100.0, 110.0]  # +10% price
    history["USDAUD=X"] = [1.40, 1.54]  # +10% fx
    # (110*1.54)/(100*1.40) - 1 = 0.21
    assert pf._period_return("AAPL", "USD", "3mo", "AUD") == pytest.approx(0.21)


def test_period_return_falls_back_to_native_without_fx(history):
    history["AAPL"] = [100.0, 110.0]
    # No USDAUD=X series -> native return rather than failure.
    assert pf._period_return("AAPL", "USD", "3mo", "AUD") == pytest.approx(0.10)


def test_period_return_none_without_history(history):
    assert pf._period_return("NOPE", "AUD", "3mo", "AUD") is None


# --------------------------------------------------------------------------- #
# Weighting helper
# --------------------------------------------------------------------------- #
def test_weighted_period_returns_basic():
    components = [
        (1000.0, {"1mo": 0.10}),
        (1000.0, {"1mo": 0.20}),
    ]
    out = pf._weighted_period_returns(components, ["1mo"])
    assert out["1mo"]["return_pct"] == 15.0
    assert out["1mo"]["coverage"] == "2/2"


def test_weighted_period_returns_renormalises_on_missing():
    components = [
        (1000.0, {"1mo": 0.10}),
        (1000.0, {"1mo": None}),  # missing data
    ]
    out = pf._weighted_period_returns(components, ["1mo"])
    assert out["1mo"]["return_pct"] == 10.0  # not diluted by the missing one
    assert out["1mo"]["coverage"] == "1/2"


def test_weighted_period_returns_all_missing():
    out = pf._weighted_period_returns([(1000.0, {"1mo": None})], ["1mo"])
    assert out["1mo"]["return_pct"] is None
    assert out["1mo"]["coverage"] == "0/1"


# --------------------------------------------------------------------------- #
# End-to-end comparison
# --------------------------------------------------------------------------- #
def test_compare_actual_equals_benchmark(session, add_holding, history):
    history["VAS.AX"] = [100.0, 110.0]
    add_holding("VAS", quantity=10, exchange="ASX")
    pf.create_benchmark_from_dict(
        session, {"name": "ASX", "constituents": [{"ticker": "VAS", "weight_pct": 100}]}
    )

    result = pf.compare_to_benchmarks(session, periods=["3mo"])
    assert result["actual"]["3mo"]["return_pct"] == 10.0

    bench = result["benchmarks"][0]
    cell = bench["periods"]["3mo"]
    assert cell["actual_return_pct"] == 10.0
    assert cell["benchmark_return_pct"] == 10.0
    assert cell["excess_return_pct"] == 0.0


def test_compare_excess_reflects_outperformance(session, add_holding, history):
    history["VAS.AX"] = [100.0, 120.0]  # actual holding +20%
    history["URTH"] = [100.0, 110.0]  # benchmark +10% (USD)
    history["USDAUD=X"] = [1.0, 1.0]  # no FX move, isolate price return
    add_holding("VAS", quantity=10, exchange="ASX")
    pf.create_benchmark_from_dict(
        session,
        {"name": "MSCI World", "constituents": [{"ticker": "URTH", "weight_pct": 100,
                                                 "exchange": "US"}]},
    )

    result = pf.compare_to_benchmarks(session, periods=["3mo"])
    cell = result["benchmarks"][0]["periods"]["3mo"]
    assert cell["actual_return_pct"] == 20.0
    assert cell["benchmark_return_pct"] == 10.0
    assert cell["excess_return_pct"] == 10.0


def test_compare_multi_constituent_benchmark(session, add_holding, history):
    # 50% IQLT + 25% IVLU + 25% IMTM, priced in AUD via .XA (no FX needed).
    history["IQLT.XA"] = [100.0, 110.0]  # +10%
    history["IVLU.XA"] = [100.0, 120.0]  # +20%
    history["IMTM.XA"] = [100.0, 140.0]  # +40%
    history["VAS.AX"] = [100.0, 100.0]
    add_holding("VAS", quantity=10, exchange="ASX")
    pf.create_benchmark_from_dict(
        session,
        {
            "name": "Factor Blend",
            "constituents": [
                {"ticker": "IQLT", "weight_pct": 50, "exchange": "CBOE_AU"},
                {"ticker": "IVLU", "weight_pct": 25, "exchange": "CBOE_AU"},
                {"ticker": "IMTM", "weight_pct": 25, "exchange": "CBOE_AU"},
            ],
        },
    )
    result = pf.compare_to_benchmarks(session, periods=["3mo"])
    cell = result["benchmarks"][0]["periods"]["3mo"]
    # 0.5*10 + 0.25*20 + 0.25*40 = 20%
    assert cell["benchmark_return_pct"] == 20.0
    assert cell["benchmark_coverage"] == "3/3"


def test_compare_no_benchmarks(session, add_holding, history):
    history["VAS.AX"] = [100.0, 110.0]
    add_holding("VAS", quantity=10, exchange="ASX")
    result = pf.compare_to_benchmarks(session, periods=["3mo"])
    assert result["benchmarks"] == []
    assert result["actual"]["3mo"]["return_pct"] == 10.0


# --------------------------------------------------------------------------- #
# HTTP endpoint
# --------------------------------------------------------------------------- #
def test_compare_endpoint(client, history):
    history["VAS.AX"] = [100.0, 110.0]
    client.post("/holdings/upload", data="ticker,quantity\nVAS,10\n",
                content_type="text/csv")
    client.post("/benchmarks/create",
                json={"name": "ASX", "constituents": [{"ticker": "VAS",
                                                       "weight_pct": 100}]})
    resp = client.get("/benchmarks/compare?periods=3mo")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["periods"] == ["3mo"]
    assert body["benchmarks"][0]["periods"]["3mo"]["excess_return_pct"] == 0.0


def test_compare_endpoint_rejects_bad_period(client):
    resp = client.get("/benchmarks/compare?periods=1mo,bogus")
    assert resp.status_code == 400
    assert "bogus" in resp.get_json()["error"]


def test_compare_endpoint_defaults_periods(client, history):
    resp = client.get("/benchmarks/compare")
    assert resp.status_code == 200
    assert resp.get_json()["periods"] == list(pf.DEFAULT_PERIODS)
