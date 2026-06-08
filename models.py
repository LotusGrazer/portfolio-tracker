"""SQLAlchemy ORM models for portfolios, holdings, and cached prices.

Schema notes / improvements over the original brief:
  * ``Holding.exchange`` was added. yfinance needs an exchange-specific symbol
    (e.g. ``VAS`` on the ASX is ``VAS.AX``; BTC is ``BTC-USD``). Storing the
    exchange lets us build the correct lookup symbol and infer the trading
    currency. It is optional in the CSV and defaults to ASX.
  * ``Price.ticker`` stores the *resolved* yfinance symbol (e.g. ``VAS.AX``),
    which makes the price cache unambiguous. FX rates are cached in the same
    table as pseudo-tickers like ``USDAUD=X``.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def utcnow() -> dt.datetime:
    """Naive UTC timestamp (avoids the deprecated ``datetime.utcnow()``)."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Portfolio(Base):
    """A named collection of holdings.

    ``type`` is either ``"actual"`` (real money we own, valued by quantity) or
    ``"benchmark"`` (a reference index/blend, defined by target weights).
    """

    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="actual")
    created_date: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow
    )

    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "created_date": self.created_date.isoformat()
            if self.created_date
            else None,
        }


class Holding(Base):
    """A single line item in a portfolio.

    For *actual* portfolios: ``quantity``, ``cost_base_per_unit``,
    ``date_acquired``, ``broker`` and ``asset_class`` are populated and
    ``weight_pct`` is NULL.

    For *benchmark* portfolios: only ``weight_pct`` is populated.
    """

    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    exchange: Mapped[str | None] = mapped_column(String, default="ASX")

    # Actual-holding fields
    quantity: Mapped[float | None] = mapped_column(Float)
    cost_base_per_unit: Mapped[float | None] = mapped_column(Float)
    date_acquired: Mapped[dt.date | None] = mapped_column(Date)
    broker: Mapped[str | None] = mapped_column(String)
    asset_class: Mapped[str | None] = mapped_column(String)

    # Benchmark field
    weight_pct: Mapped[float | None] = mapped_column(Float)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "portfolio_id": self.portfolio_id,
            "ticker": self.ticker,
            "exchange": self.exchange,
            "quantity": self.quantity,
            "cost_base_per_unit": self.cost_base_per_unit,
            "date_acquired": self.date_acquired.isoformat()
            if self.date_acquired
            else None,
            "broker": self.broker,
            "asset_class": self.asset_class,
            "weight_pct": self.weight_pct,
        }


class Price(Base):
    """Cached last-traded price (or FX rate) for a resolved yfinance symbol."""

    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str | None] = mapped_column(String)
    last_updated: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow
    )

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "currency": self.currency,
            "last_updated": self.last_updated.isoformat()
            if self.last_updated
            else None,
        }
