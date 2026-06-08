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


def test_oversell_returns_400(client):
    csv_data = (
        "ticker,type,quantity,price_per_unit,trade_date\n"
        "AOV,buy,50,2.00,2023-01-01\n"
        "AOV,sell,80,3.00,2023-06-01\n"
    )
    client.post("/transactions/upload", data=csv_data, content_type="text/csv")
    resp = client.get("/portfolio/realised")
    assert resp.status_code == 400
    assert "oversell" in resp.get_json()["error"]
