"""Pricing, FX conversion, caching/TTL, and graceful degradation."""
import datetime as dt

import pytest

import config
import portfolio as pf
from models import Price, utcnow


def test_value_holding_aud(session, add_holding):
    h = add_holding("VAS", quantity=10, exchange="ASX", cost=90.0)
    result = pf.value_holding(session, h)
    assert result["current_price"] == 100.0
    assert result["price_currency"] == "AUD"
    assert result["fx_rate_to_base"] == 1.0
    assert result["market_value"] == 1000.0
    assert result["market_value_base"] == 1000.0
    assert result["cost_base_total"] == 900.0
    assert result["gain_loss_base"] == 100.0
    assert result["gain_loss_pct"] == pytest.approx(100 / 900 * 100)


def test_value_holding_usd_converted_to_aud(session, add_holding):
    # AAPL: 300 USD * 20 = 6000 USD; FX 1.5 -> 9000 AUD.
    h = add_holding("AAPL", quantity=20, exchange="US", cost=150.0)
    result = pf.value_holding(session, h)
    assert result["market_value"] == 6000.0  # native USD
    assert result["market_value_base"] == 9000.0  # AUD
    assert result["cost_base_total"] == 3000.0
    assert result["cost_base_total_base"] == 4500.0
    assert result["gain_loss_base"] == 4500.0
    assert result["gain_loss_pct"] == 100.0


def test_get_fx_rate_same_currency_is_one(session):
    assert pf.get_fx_rate(session, "AUD") == 1.0


def test_get_fx_rate_cross_currency(session):
    assert pf.get_fx_rate(session, "USD") == 1.5


def test_price_is_cached_within_ttl(session, add_holding, market):
    h = add_holding("VAS", quantity=10, exchange="ASX")
    pf.value_holding(session, h)
    pf.value_holding(session, h)
    # VAS.AX fetched once; the second valuation uses the cached row.
    assert market.calls.count("VAS.AX") == 1


def test_stale_price_refetched_after_ttl(session, add_holding, market):
    h = add_holding("VAS", quantity=10, exchange="ASX")
    pf.value_holding(session, h)

    # Age the cached row past the TTL.
    row = session.query(Price).filter_by(ticker="VAS.AX").one()
    row.last_updated = utcnow() - dt.timedelta(
        minutes=config.PRICE_CACHE_TTL_MINUTES + 1
    )
    session.commit()

    pf.value_holding(session, h)
    assert market.calls.count("VAS.AX") == 2


def test_stale_if_error_returns_last_cached_price(session, add_holding, market):
    h = add_holding("VAS", quantity=10, exchange="ASX")
    pf.value_holding(session, h)  # caches 100.0

    # Expire the cache and make the next live fetch fail.
    row = session.query(Price).filter_by(ticker="VAS.AX").one()
    row.last_updated = utcnow() - dt.timedelta(hours=1)
    session.commit()
    market.fail.add("VAS.AX")

    result = pf.value_holding(session, h)
    assert result["current_price"] == 100.0  # served stale rather than failing


def test_unpriced_holding_returns_none_not_error(session, add_holding):
    # NOPE.AX isn't in the fake market and has no cache -> graceful nulls.
    h = add_holding("NOPE", quantity=10, exchange="ASX", cost=5.0)
    result = pf.value_holding(session, h)
    assert result["current_price"] is None
    assert result["market_value_base"] is None
    assert result["gain_loss_base"] is None
