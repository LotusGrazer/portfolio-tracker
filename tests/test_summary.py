"""Portfolio summary: totals, breakdowns, and weighting."""
import portfolio as pf


def test_summary_totals_and_breakdowns(session, add_holding):
    # VAS: 10 * 100 AUD          = 1000 AUD
    # AAPL: 10 * 300 USD * 1.5   = 4500 AUD
    add_holding("VAS", quantity=10, exchange="ASX", cost=90.0, asset_class="etf",
                broker="Commsec")
    add_holding("AAPL", quantity=10, exchange="US", cost=150.0, asset_class="stock",
                broker="IBKR")

    summary = pf.portfolio_summary(session)
    assert summary["base_currency"] == "AUD"
    assert summary["total_market_value"] == 5500.0
    assert summary["holdings_count"] == 2
    assert summary["holdings_priced"] == 2
    assert summary["unpriced_tickers"] == []

    # cost: VAS 900 AUD + AAPL (1500 USD * 1.5) 2250 AUD = 3150
    assert summary["total_cost_base"] == 3150.0
    assert summary["total_gain_loss"] == 2350.0

    by_currency = {row["key"]: row for row in summary["by_currency"]}
    assert by_currency["AUD"]["value"] == 1000.0
    assert by_currency["USD"]["value"] == 4500.0
    # Largest bucket (USD) is sorted first and weighted correctly.
    assert summary["by_currency"][0]["key"] == "USD"
    assert by_currency["USD"]["weight_pct"] == round(4500 / 5500 * 100, 2)

    by_asset = {row["key"]: row["value"] for row in summary["by_asset_class"]}
    assert by_asset == {"etf": 1000.0, "stock": 4500.0}


def test_summary_lists_unpriced(session, add_holding):
    add_holding("VAS", quantity=10, exchange="ASX")
    add_holding("NOPE", quantity=5, exchange="ASX")  # not in fake market
    summary = pf.portfolio_summary(session)
    assert summary["holdings_count"] == 2
    assert summary["holdings_priced"] == 1
    assert summary["unpriced_tickers"] == ["NOPE"]


def test_empty_portfolio_summary(session):
    summary = pf.portfolio_summary(session)
    assert summary["total_market_value"] == 0
    assert summary["holdings_count"] == 0
    assert summary["total_gain_loss"] is None


def test_benchmark_holdings_excluded_from_summary(session, add_holding):
    add_holding("VAS", quantity=10, exchange="ASX")
    pf.create_benchmark_from_dict(
        session, {"name": "ASX200", "constituents": [{"ticker": "VAS", "weight_pct": 100}]}
    )
    summary = pf.portfolio_summary(session)
    # Only the actual holding counts, not the benchmark constituent.
    assert summary["holdings_count"] == 1
    assert summary["total_market_value"] == 1000.0
