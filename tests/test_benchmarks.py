"""Benchmark creation (CSV + JSON), listing, weights, and name collisions."""
import pytest

import portfolio as pf
from models import Portfolio

BENCHMARK_CSV = (
    "name,ticker,weight_pct,exchange\n"
    "ASX200,VAS,100,ASX\n"
    "60/40 ASX/US,VAS,60,ASX\n"
    "60/40 ASX/US,VGS,40,ASX\n"
)


def test_create_benchmarks_from_csv_groups_by_name(session):
    results = pf.create_benchmark_from_csv(session, BENCHMARK_CSV)
    by_name = {r["name"]: r for r in results}
    assert set(by_name) == {"ASX200", "60/40 ASX/US"}
    assert len(by_name["60/40 ASX/US"]["constituents"]) == 2
    assert by_name["ASX200"]["total_weight_pct"] == 100.0
    assert "warning" not in by_name["60/40 ASX/US"]


def test_create_benchmark_from_json(session):
    result = pf.create_benchmark_from_dict(
        session,
        {
            "name": "Tech",
            "constituents": [
                {"ticker": "AAPL", "weight_pct": 50, "exchange": "US"},
                {"ticker": "VAS", "weight_pct": 50},
            ],
        },
    )
    assert result["type"] == "benchmark"
    assert result["total_weight_pct"] == 100.0
    bench = session.query(Portfolio).filter_by(name="Tech").one()
    assert {h.ticker for h in bench.holdings} == {"AAPL", "VAS"}
    assert {h.exchange for h in bench.holdings} == {"US", "ASX"}


def test_weight_warning_when_not_100(session):
    result = pf.create_benchmark_from_dict(
        session, {"name": "Off", "constituents": [{"ticker": "VAS", "weight_pct": 90}]}
    )
    assert "warning" in result
    assert "90" in result["warning"]


def test_recreating_benchmark_replaces_constituents(session):
    pf.create_benchmark_from_dict(
        session, {"name": "B", "constituents": [{"ticker": "VAS", "weight_pct": 100}]}
    )
    pf.create_benchmark_from_dict(
        session, {"name": "B", "constituents": [{"ticker": "AAPL", "weight_pct": 100,
                                                 "exchange": "US"}]}
    )
    bench = session.query(Portfolio).filter_by(name="B").one()
    assert {h.ticker for h in bench.holdings} == {"AAPL"}


def test_name_collision_with_actual_portfolio_raises(session):
    # The default "My Portfolio" is an actual portfolio.
    import config

    with pytest.raises(pf.PortfolioError, match="actual portfolio"):
        pf.create_benchmark_from_dict(
            session,
            {"name": config.DEFAULT_PORTFOLIO,
             "constituents": [{"ticker": "VAS", "weight_pct": 100}]},
        )


def test_list_benchmarks(session):
    pf.create_benchmark_from_csv(session, BENCHMARK_CSV)
    benchmarks = pf.list_benchmarks(session)
    names = {b["name"] for b in benchmarks}
    assert names == {"ASX200", "60/40 ASX/US"}
    for b in benchmarks:
        assert "constituents" in b
        assert "total_weight_pct" in b


def test_zero_total_weight_rejected(session):
    with pytest.raises(pf.PortfolioError, match="positive total"):
        pf.create_benchmark_from_dict(
            session, {"name": "Zero", "constituents": [{"ticker": "URTH", "weight_pct": 0}]}
        )


def test_delete_benchmark(session):
    created = pf.create_benchmark_from_dict(
        session, {"name": "Temp", "constituents": [{"ticker": "VAS", "weight_pct": 100}]}
    )
    result = pf.delete_benchmark(session, created["id"])
    assert result["deleted"] == "Temp"
    assert pf.list_benchmarks(session) == []


def test_delete_unknown_benchmark_raises(session):
    with pytest.raises(pf.PortfolioError, match="no benchmark"):
        pf.delete_benchmark(session, 9999)


def test_delete_endpoint(client):
    created = client.post(
        "/benchmarks/create",
        json={"name": "Temp", "constituents": [{"ticker": "VAS", "weight_pct": 100}]},
    ).get_json()
    resp = client.delete(f"/benchmarks/{created['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == "Temp"
    assert client.get("/benchmarks").get_json() == []


def test_missing_required_csv_columns_raises(session):
    with pytest.raises(pf.PortfolioError, match="must include"):
        pf.create_benchmark_from_csv(session, "name,ticker\nASX200,VAS\n")


def test_json_missing_fields_raises(session):
    with pytest.raises(pf.PortfolioError):
        pf.create_benchmark_from_dict(session, {"name": "X"})
    with pytest.raises(pf.PortfolioError, match="weight_pct"):
        pf.create_benchmark_from_dict(
            session, {"name": "X", "constituents": [{"ticker": "VAS"}]}
        )
