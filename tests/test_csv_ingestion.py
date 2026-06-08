"""CSV ingestion: validation, defaults, per-row error handling, replace."""
import datetime as dt

import pytest

import config
import portfolio as pf
from models import Holding, Portfolio

GOOD_CSV = (
    "ticker,quantity,cost_base_per_unit,date_acquired,broker,asset_class,exchange\n"
    "AOV,500,2.50,2023-06-15,IBKR,stock,ASX\n"
    "VAS,1000,90.00,2022-03-01,Commsec,etf,ASX\n"
)


def test_ingest_valid_csv(session):
    result = pf.ingest_holdings_csv(session, GOOD_CSV)
    assert result.added == 2
    assert result.skipped == 0
    assert result.errors == []

    holdings = session.query(Holding).all()
    by_ticker = {h.ticker: h for h in holdings}
    assert by_ticker["AOV"].quantity == 500
    assert by_ticker["AOV"].cost_base_per_unit == 2.50
    assert by_ticker["AOV"].date_acquired == dt.date(2023, 6, 15)
    assert by_ticker["VAS"].asset_class == "etf"


def test_defaults_applied(session):
    # No exchange or asset_class columns -> defaults ASX / stock.
    pf.ingest_holdings_csv(session, "ticker,quantity\nXYZ,10\n")
    h = session.query(Holding).filter_by(ticker="XYZ").one()
    assert h.exchange == "ASX"
    assert h.asset_class == "stock"


def test_ticker_uppercased(session):
    pf.ingest_holdings_csv(session, "ticker,quantity\nvas,10\n")
    assert session.query(Holding).filter_by(ticker="VAS").one()


def test_missing_ticker_column_raises(session):
    with pytest.raises(pf.PortfolioError, match="ticker"):
        pf.ingest_holdings_csv(session, "quantity,broker\n10,IBKR\n")


def test_bad_rows_skipped_not_fatal(session):
    csv_data = (
        "ticker,quantity\n"
        "GOOD,10\n"
        ",5\n"  # missing ticker
        "BADQTY,notanumber\n"  # invalid quantity
        "NOQTY,\n"  # missing required quantity
    )
    result = pf.ingest_holdings_csv(session, csv_data)
    assert result.added == 1
    assert result.skipped == 3
    rows_with_errors = {e["row"] for e in result.errors}
    assert rows_with_errors == {3, 4, 5}
    assert session.query(Holding).filter_by(ticker="GOOD").one()


@pytest.mark.parametrize(
    "raw_date,expected",
    [
        ("2023-06-15", dt.date(2023, 6, 15)),
        ("15/06/2023", dt.date(2023, 6, 15)),
    ],
)
def test_date_formats(session, raw_date, expected):
    pf.ingest_holdings_csv(
        session, f"ticker,quantity,date_acquired\nAOV,10,{raw_date}\n"
    )
    assert session.query(Holding).filter_by(ticker="AOV").one().date_acquired == expected


def test_invalid_date_skips_row(session):
    result = pf.ingest_holdings_csv(
        session, "ticker,quantity,date_acquired\nAOV,10,not-a-date\n"
    )
    assert result.added == 0
    assert "date" in result.errors[0]["error"]


def test_replace_clears_existing(session):
    pf.ingest_holdings_csv(session, "ticker,quantity\nOLD,1\n")
    pf.ingest_holdings_csv(session, "ticker,quantity\nNEW,2\n", replace=True)
    tickers = {h.ticker for h in session.query(Holding).all()}
    assert tickers == {"NEW"}


def test_append_without_replace(session):
    pf.ingest_holdings_csv(session, "ticker,quantity\nA,1\n")
    pf.ingest_holdings_csv(session, "ticker,quantity\nB,2\n")
    tickers = {h.ticker for h in session.query(Holding).all()}
    assert tickers == {"A", "B"}


def test_custom_portfolio_created(session):
    pf.ingest_holdings_csv(session, "ticker,quantity\nA,1\n", portfolio_name="Wife")
    assert session.query(Portfolio).filter_by(name="Wife", type="actual").one()


def test_cost_currency_column_parsed(session):
    pf.ingest_holdings_csv(
        session,
        "ticker,quantity,cost_base_per_unit,cost_currency\n"
        "AAPL,10,100,usd\n"  # lowercased -> normalised to USD
        "VAS,10,90,\n",  # blank -> None (defaults to base at valuation time)
    )
    by_ticker = {h.ticker: h for h in session.query(Holding).all()}
    assert by_ticker["AAPL"].cost_currency == "USD"
    assert by_ticker["VAS"].cost_currency is None


def test_bom_and_thousands_separator(session):
    # utf-8 BOM prefix + comma thousands separator in quantity.
    raw = "﻿ticker,quantity\nAOV,\"1,500\"\n".encode("utf-8")
    pf.ingest_holdings_csv(session, raw)
    assert session.query(Holding).filter_by(ticker="AOV").one().quantity == 1500.0
