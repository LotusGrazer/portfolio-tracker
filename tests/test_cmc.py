"""CMC 'Cash Transaction Summary' parsing and auto-detected import."""
import ledger
from models import Transaction


# --------------------------------------------------------------------------- #
# Description parsing
# --------------------------------------------------------------------------- #
def test_parse_buy_asx():
    out = ledger.parse_cmc_description("Bght 154 VGMF @ 64.6100 17284978")
    assert out == {
        "type": "buy",
        "ticker": "VGMF",
        "exchange": "ASX",
        "quantity": 154.0,
        "price_per_unit": 64.61,
        "reference": "17284978",
    }


def test_parse_sell_with_aud():
    out = ledger.parse_cmc_description("Sold 125 VGAD @ 80.0800 AUD 21591579")
    assert out["type"] == "sell"
    assert out["quantity"] == 125.0
    assert out["price_per_unit"] == 80.08
    assert out["exchange"] == "ASX"


def test_parse_us_market_suffix():
    out = ledger.parse_cmc_description("Bght 10 AAPL:US @ 257.4110 AUD 25664103")
    assert out["ticker"] == "AAPL"
    assert out["exchange"] == "US"


def test_parse_cboe_au_ticker():
    out = ledger.parse_cmc_description("Bght 20 IQLT @ 28.5200 AUD 30261971")
    assert out["exchange"] == "CBOE_AU"


def test_parse_alphanumeric_ticker():
    out = ledger.parse_cmc_description("Bght 3333 AL3 @ 0.1700 AUD 26971218")
    assert out["ticker"] == "AL3"
    assert out["quantity"] == 3333.0


def test_non_trade_rows_return_none():
    for desc in [
        "OPENING BALANCE",
        "MACQUARIE CMA INTEREST PAID",
        "MR MAX JOHNSON Trading deposit",
        "VEU DIVIDEND VEU58/00826899",
        "JNL2524210 AAPL:US Intl Div  Ex:12/08/24",
        "To Max Johnson - Internal transfer",
        "TOTALS",
    ]:
        assert ledger.parse_cmc_description(desc) is None


# --------------------------------------------------------------------------- #
# Auto-detection + import
# --------------------------------------------------------------------------- #
CMC_CSV = (
    "Date,Description,Debit $,Credit $,Balance $\n"
    "9/5/2020,OPENING BALANCE,,,\n"
    "29/10/2021,MACQUARIE CMA INTEREST PAID,,,\n"
    "9/12/2021,Bght 100 VGMF @ 2.0000 17284978,,,\n"
    "12/3/2024,Bght 10 AAPL:US @ 257.4110 AUD 25664103,,,\n"
    "13/3/2025,Bght 20 IQLT @ 28.5200 AUD 30261971,,,\n"
    "31/1/2023,Sold 100 VGMF @ 3.0000 AUD 21591579,,,\n"
    ",TOTALS,10000,10000,\n"
)


def test_cmc_auto_detected_and_imported(session):
    result = ledger.ingest_transactions_csv(session, CMC_CSV)
    assert result.added == 4  # 3 buys + 1 sell
    assert result.skipped == 3  # opening balance, interest, totals
    assert result.errors == []

    txns = {t.ticker: t for t in session.query(Transaction).all()}
    assert txns["AAPL"].exchange == "US"
    assert txns["IQLT"].exchange == "CBOE_AU"
    assert txns["VGMF"].exchange == "ASX"
    # CMC prices are AUD -> currency stored as None (base).
    assert txns["AAPL"].currency is None


def test_cmc_australian_date_parsing(session):
    ledger.ingest_transactions_csv(session, CMC_CSV)
    vgmf_buy = (
        session.query(Transaction)
        .filter_by(ticker="VGMF", type="buy")
        .one()
    )
    # 9/12/2021 is 9 December 2021 (DD/MM/YYYY), not 12 September.
    assert vgmf_buy.trade_date.isoformat() == "2021-12-09"


def test_cmc_fee_derived_from_cash_columns(session):
    # Debit on a buy = consideration + brokerage; Credit on a sell = consideration - brokerage.
    csv_data = (
        "Date,Description,Debit $,Credit $,Balance $\n"
        "1/1/2023,Bght 100 AOV @ 2.0000 111,210.00,,\n"  # 200 + 10 fee
        "1/6/2024,Sold 100 AOV @ 3.0000 AUD 222,,290.00,\n"  # 300 - 10 fee
    )
    ledger.ingest_transactions_csv(session, csv_data)
    txns = {t.type: t for t in session.query(Transaction).all()}
    assert txns["buy"].fee == 10.0
    assert txns["sell"].fee == 10.0


def test_cmc_replace(session):
    ledger.ingest_transactions_csv(session, CMC_CSV)
    ledger.ingest_transactions_csv(session, CMC_CSV, replace=True)
    # Replace, not append -> still 4.
    assert session.query(Transaction).count() == 4
