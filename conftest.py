"""Shared pytest fixtures.

Two hard rules this file enforces for the whole suite:

1. **No network.** ``portfolio._fetch_live_price`` is the single seam where we
   talk to yfinance. An autouse fixture replaces it with an in-memory fake, so
   no test can accidentally hit Yahoo.
2. **No real database.** ``DATABASE_URL`` is pointed at a throwaway temp file
   *before* any app module is imported, so the real ``portfolio.db`` is never
   touched. Tables are dropped and recreated before every test for isolation.
"""
from __future__ import annotations

import os
import tempfile

# Must happen before importing config/database/app, which read this at import.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="portfolio_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ.setdefault("BASE_CURRENCY", "AUD")
os.environ.setdefault("PRICE_CACHE_TTL_MINUTES", "15")

import pytest  # noqa: E402

import config  # noqa: E402
import portfolio as pf  # noqa: E402
from app import app as flask_app  # noqa: E402
from database import SessionLocal, engine, ensure_portfolio  # noqa: E402
from models import Base, Holding  # noqa: E402


def pytest_unconfigure(config):  # noqa: ARG001
    """Remove the temp database file when the session ends."""
    try:
        os.close(_DB_FD)
    except OSError:
        pass
    if os.path.exists(_DB_PATH):
        os.remove(_DB_PATH)


# --------------------------------------------------------------------------- #
# Database isolation
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def reset_db():
    """Drop + recreate all tables and the default portfolio before each test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        ensure_portfolio(s, config.DEFAULT_PORTFOLIO, "actual")
        s.commit()
    yield


@pytest.fixture
def session():
    """A plain SQLAlchemy session for exercising portfolio.py directly."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Fake market (no network)
# --------------------------------------------------------------------------- #
class FakeMarket:
    """Deterministic stand-in for yfinance price lookups.

    Maps a resolved symbol (e.g. ``VAS.AX``, ``USDAUD=X``) to
    ``(price, currency)``. Symbols added to ``fail`` raise PriceLookupError;
    unknown symbols also raise. ``calls`` records every lookup so tests can
    assert on caching behaviour.
    """

    def __init__(self):
        self.prices: dict[str, tuple[float, str | None]] = {
            "VAS.AX": (100.0, "AUD"),
            "AOV.AX": (6.0, "AUD"),
            "AAPL": (300.0, "USD"),
            "BTC-USD": (60000.0, "USD"),
            "USDAUD=X": (1.5, "AUD"),  # 1 USD = 1.5 AUD
        }
        self.fail: set[str] = set()
        self.calls: list[str] = []

    def fetch(self, symbol: str) -> tuple[float, str | None]:
        self.calls.append(symbol)
        if symbol in self.fail or symbol not in self.prices:
            raise pf.PriceLookupError(symbol)
        return self.prices[symbol]


@pytest.fixture(autouse=True)
def market(monkeypatch):
    """Replace the live price fetch with the fake market for every test."""
    fake = FakeMarket()
    monkeypatch.setattr(pf, "_fetch_live_price", fake.fetch)
    return fake


# --------------------------------------------------------------------------- #
# Convenience fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


@pytest.fixture
def add_holding(session):
    """Add an actual holding to the default portfolio and return it."""

    def _add(ticker, quantity, exchange="ASX", cost=None, cost_currency=None, **kwargs):
        portfolio = ensure_portfolio(session, config.DEFAULT_PORTFOLIO, "actual")
        holding = Holding(
            portfolio_id=portfolio.id,
            ticker=ticker,
            exchange=exchange,
            quantity=quantity,
            cost_base_per_unit=cost,
            cost_currency=cost_currency,
            asset_class=kwargs.get("asset_class", "stock"),
            broker=kwargs.get("broker"),
        )
        session.add(holding)
        session.commit()
        return holding

    return _add
