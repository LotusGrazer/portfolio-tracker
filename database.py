"""Database engine, session management, and initialization."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import config
from models import Base, Portfolio

engine = create_engine(
    config.DATABASE_URL,
    future=True,
    echo=False,
    # SQLite + Flask's dev server can touch the connection from worker threads.
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _connection_record):
    """SQLite ignores foreign keys unless this PRAGMA is set per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    """Create tables (idempotent) and ensure the default portfolio exists."""
    Base.metadata.create_all(engine)
    with session_scope() as session:
        ensure_portfolio(session, config.DEFAULT_PORTFOLIO, "actual")


def ensure_portfolio(session: Session, name: str, ptype: str) -> Portfolio:
    """Return the portfolio with ``name``, creating it if necessary."""
    portfolio = session.query(Portfolio).filter_by(name=name).one_or_none()
    if portfolio is None:
        portfolio = Portfolio(name=name, type=ptype)
        session.add(portfolio)
        session.flush()
    return portfolio


@contextmanager
def session_scope():
    """Transactional session scope: commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
