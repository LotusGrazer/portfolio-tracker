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
        # Cboe Australia cross-quotes resolve to the underlying US listing.
        ("IQLT", "CBOE_AU", "IQLT", "USD"),
        ("IVLU", "XA", "IVLU", "USD"),
        ("IMTM", "CHIA", "IMTM", "USD"),
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
