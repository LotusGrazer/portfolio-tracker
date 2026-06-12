"""Transaction ledger DB + API: CSV import, realised/CGT, FY filter, sync."""
import pytest

import ledger
from models import Holding, Transaction


# --------------------------------------------------------------------------- #
# CSV import
# --------------------------------------------------------------------------- #
GOOD_CSV = (
    "ticker,type,quantity,price_per_unit,trade_date,exchange,fee,reference\n"
    "AOV,buy,500,2.50,2023-01-01,ASX,,REF1\n"
    "AOV,sell,200,4.00,2024-06-01,ASX,,REF2\n"
)


def test_ingest_transactions_csv(session):
    result = ledger.ingest_transactions_csv(session, GOOD_CSV)
    assert result.added == 2
    assert result.skipped == 0
    txns = session.query(Transaction).order_by(Transaction.trade_date).all()
    assert [t.type for t in txns] == ["buy", "sell"]
    assert txns[0].reference == "REF1"


def test_ingest_missing_required_column(session):
    with pytest.raises(ledger.PortfolioError, match="missing column"):
        ledger.ingest_transactions_csv(session, "ticker,quantity\nAOV,10\n")


def test_ingest_validates_rows(session):
    csv_data = (
        "ticker,type,quantity,price_per_unit,trade_date\n"
        "AOV,buy,100,2.00,2023-01-01\n"
        "AOV,hold,100,2.00,2023-01-01\n"  # bad type
        "AOV,buy,-5,2.00,2023-01-01\n"  # non-positive qty
        "AOV,sell,100,2.00,not-a-date\n"  # bad date
    )
    result = ledger.ingest_transactions_csv(session, csv_data)
    assert result.added == 1
    assert result.skipped == 3
    rows = {e["row"] for e in result.errors}
    assert rows == {3, 4, 5}


def test_ingest_replace(session):
    ledger.ingest_transactions_csv(session, GOOD_CSV)
    ledger.ingest_transactions_csv(
        session,
        "ticker,type,quantity,price_per_unit,trade_date\nVAS,buy,1,1,2023-01-01\n",
        replace=True,
    )
    tickers = {t.ticker for t in session.query(Transaction).all()}
    assert tickers == {"VAS"}


# --------------------------------------------------------------------------- #
# Realised gains + CGT
# --------------------------------------------------------------------------- #
def test_compute_realised_totals(session, add_transaction):
    add_transaction("AOV", "buy", 100, 2.00, "2022-01-01")
    add_transaction("AOV", "sell", 100, 3.00, "2023-06-01")  # held > 1yr
    result = ledger.compute_realised(session)
    assert len(result["events"]) == 1
    cgt = result["cgt_estimate"]
    assert cgt["total_realised_gain"] == 100.0
    assert cgt["discount_eligible_gain"] == 100.0
    assert cgt["estimated_discount"] == 50.0
    assert cgt["estimated_net_capital_gain"] == 50.0


def test_compute_realised_short_term_no_discount(session, add_transaction):
    add_transaction("AOV", "buy", 100, 2.00, "2023-01-01")
    add_transaction("AOV", "sell", 100, 3.00, "2023-06-01")  # held < 1yr
    cgt = ledger.compute_realised(session)["cgt_estimate"]
    assert cgt["short_term_gain"] == 100.0
    assert cgt["discount_eligible_gain"] == 0.0
    assert cgt["estimated_net_capital_gain"] == 100.0


def test_compute_realised_financial_year_filter(session, add_transaction):
    add_transaction("AOV", "buy", 200, 2.00, "2022-01-01")
    add_transaction("AOV", "sell", 100, 3.00, "2023-03-01")  # FY 2022-23
    add_transaction("AOV", "sell", 100, 4.00, "2024-03-01")  # FY 2023-24
    fy2223 = ledger.compute_realised(session, financial_year="2022-23")
    fy2324 = ledger.compute_realised(session, financial_year="2023-24")
    assert len(fy2223["events"]) == 1
    assert fy2223["cgt_estimate"]["total_realised_gain"] == 100.0
    assert fy2324["cgt_estimate"]["total_realised_gain"] == 200.0


def test_compute_realised_groups_by_currency(session, add_transaction):
    add_transaction("AAPL", "buy", 10, 100.0, "2022-01-01", exchange="US", currency="USD")
    add_transaction("AAPL", "sell", 10, 150.0, "2023-06-01", exchange="US", currency="USD")
    result = ledger.compute_realised(session)
    assert result["by_currency"]["USD"]["gain"] == 500.0


def test_realised_includes_tax_estimate_when_income_given(session, add_transaction):
    add_transaction("AOV", "buy", 1000, 2.00, "2022-01-01")
    add_transaction("AOV", "sell", 1000, 3.00, "2023-12-01")  # +1000 gain, eligible
    # net capital gain = 1000 - 500 discount = 500
    result = ledger.compute_realised(
        session, financial_year="2023-24", taxable_income=100_000
    )
    cgt = result["cgt_estimate"]
    assert cgt["estimated_net_capital_gain"] == 500.0
    # FY 2023-24 uses the 32.5% bracket at $100k: 500 @ 32.5% + 2% MC = 172.5
    assert cgt["estimated_tax"]["additional_tax"] == pytest.approx(172.5)


def test_realised_omits_tax_estimate_without_income(session, add_transaction):
    add_transaction("AOV", "buy", 100, 2.00, "2022-01-01")
    add_transaction("AOV", "sell", 100, 3.00, "2023-06-01")
    result = ledger.compute_realised(session)
    assert "estimated_tax" not in result["cgt_estimate"]


def test_oversell_on_one_ticker_warns_but_others_compute(session, add_transaction):
    # BAD oversells (no buy); AOV is clean. One bad ticker must not break the rest.
    add_transaction("BAD", "sell", 10, 5.00, "2023-06-01")
    add_transaction("AOV", "buy", 100, 2.00, "2022-01-01")
    add_transaction("AOV", "sell", 100, 3.00, "2023-06-01")
    result = ledger.compute_realised(session)
    assert any("BAD" in w for w in result["warnings"])
    assert result["cgt_estimate"]["total_realised_gain"] == 100.0  # AOV still counted


# --------------------------------------------------------------------------- #
# Sync holdings from ledger
# --------------------------------------------------------------------------- #
def test_sync_holdings_from_transactions(session, add_transaction):
    add_transaction("AOV", "buy", 500, 2.50, "2023-01-01")
    add_transaction("AOV", "buy", 300, 3.10, "2023-06-01")
    add_transaction("AOV", "sell", 200, 4.00, "2024-01-01")  # FIFO: removes 200 @2.50

    summary = ledger.sync_holdings_from_transactions(session)
    assert summary["holdings_created"] == 2  # 300 @2.50 + 300 @3.10

    holdings = session.query(Holding).order_by(Holding.cost_base_per_unit).all()
    assert [(h.quantity, h.cost_base_per_unit) for h in holdings] == [
        (300, 2.50),
        (300, 3.10),
    ]
    # Acquisition dates are preserved per parcel.
    assert {h.date_acquired.isoformat() for h in holdings} == {
        "2023-01-01",
        "2023-06-01",
    }


def test_sync_replaces_existing_holdings(session, add_holding, add_transaction):
    add_holding("OLD", quantity=1)  # manual holding, should be replaced
    add_transaction("AOV", "buy", 100, 2.00, "2023-01-01")
    ledger.sync_holdings_from_transactions(session)
    tickers = {h.ticker for h in session.query(Holding).all()}
    assert tickers == {"AOV"}


# --------------------------------------------------------------------------- #
# HTTP endpoints
# --------------------------------------------------------------------------- #
def test_transactions_endpoints(client):
    resp = client.post("/transactions/upload", data=GOOD_CSV, content_type="text/csv")
    assert resp.status_code == 201
    assert resp.get_json()["added"] == 2

    listing = client.get("/transactions").get_json()
    assert len(listing) == 2
    # Newest trade first.
    assert listing[0]["type"] == "sell"


def test_realised_endpoint(client):
    client.post("/transactions/upload", data=GOOD_CSV, content_type="text/csv")
    body = client.get("/portfolio/realised?financial_year=2023-24").get_json()
    assert body["financial_year"] == "2023-24"
    # 200 sold @4.00 from a 2.50 parcel held > 1yr -> $300 gain, eligible.
    assert body["cgt_estimate"]["total_realised_gain"] == 300.0
    assert body["cgt_estimate"]["estimated_discount"] == 150.0


def test_sync_endpoint_then_holdings(client):
    client.post("/transactions/upload", data=GOOD_CSV, content_type="text/csv")
    synced = client.post("/transactions/sync-holdings").get_json()
    assert synced["holdings_created"] == 1  # 300 AOV left after the sell
    holdings = client.get("/holdings").get_json()
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "AOV"
    assert holdings[0]["quantity"] == 300


def test_oversell_reported_as_warning_not_error(client):
    # A data gap (oversell) is surfaced as a warning, not a hard failure, so the
    # rest of the portfolio still reports.
    csv_data = (
        "ticker,type,quantity,price_per_unit,trade_date\n"
        "AOV,buy,50,2.00,2023-01-01\n"
        "AOV,sell,80,3.00,2023-06-01\n"
    )
    client.post("/transactions/upload", data=csv_data, content_type="text/csv")
    resp = client.get("/portfolio/realised")
    assert resp.status_code == 200
    assert any("oversell" in w for w in resp.get_json()["warnings"])


def test_same_day_buy_and_sell_inserted_sell_first(session, add_transaction):
    # Row order in the database must not decide FIFO order: the sell is
    # inserted first but shares the buy's trade date, so it must not oversell.
    add_transaction("AOV", "sell", 100, 3.00, "2023-06-01")
    add_transaction("AOV", "buy", 100, 2.00, "2023-06-01")
    result = ledger.compute_realised(session)
    assert result["warnings"] == []
    assert len(result["events"]) == 1
    assert result["events"][0]["gain"] == 100.0
