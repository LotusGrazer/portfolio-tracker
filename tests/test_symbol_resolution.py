"""Symbol resolution: friendly ticker + exchange -> yfinance symbol/currency."""
import pytest

import portfolio as pf


@pytest.mark.parametrize(
    "ticker,exchange,expected_symbol,expected_currency",
    [
        ("VAS", "ASX", "VAS.AX", "AUD"),
        ("vas", "asx", "VAS.AX", "AUD"),  # case-insensitive
        ("  AOV ", "ASX", "AOV.AX", "AUD"),  # trims whitespace
        ("AAPL", "US", "AAPL", "USD"),
        ("AAPL", "NASDAQ", "AAPL", "USD"),
        ("AAPL", "NYSE", "AAPL", "USD"),
        ("BTC", "CRYPTO", "BTC-USD", "USD"),
        # Cboe Australia listings resolve to Yahoo's ".XA" suffix, priced in AUD.
        ("IQLT", "CBOE_AU", "IQLT.XA", "AUD"),
        ("IVLU", "XA", "IVLU.XA", "AUD"),
        ("IMTM", "CHIA", "IMTM.XA", "AUD"),
        # RAW passes the symbol through untouched (e.g. an index).
        ("^AXJO", "RAW", "^AXJO", None),
        ("VAS", None, "VAS.AX", "AUD"),  # defaults to ASX
        ("VAS", "UNKNOWN", "VAS.AX", "AUD"),  # unknown -> default ASX
    ],
)
def test_resolve_symbol(ticker, exchange, expected_symbol, expected_currency):
    symbol, currency = pf.resolve_symbol(ticker, exchange)
    assert symbol == expected_symbol
    assert currency == expected_currency
