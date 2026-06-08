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
    """Per-connection SQLite tuning.

    The threaded dev server can issue parallel requests that both touch the
    price cache, so WAL mode (concurrent reader + one writer) plus a busy
    timeout (wait, don't immediately error, on a write lock) prevent spurious
    "database is locked" failures. Foreign keys are off by default in SQLite.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


# Columns added after the initial release, applied to pre-existing databases.
# SQLite's ALTER TABLE ADD COLUMN is the simplest forward-only migration that
# keeps existing data intact (create_all never alters existing tables).
_ADDED_COLUMNS = {
    "portfolio_holdings": {
        "cost_currency": "VARCHAR",
    },
}


def init_db() -> None:
    """Create tables (idempotent), run migrations, ensure default portfolio."""
    Base.metadata.create_all(engine)
    _apply_migrations()
    with session_scope() as session:
        ensure_portfolio(session, config.DEFAULT_PORTFOLIO, "actual")


def _apply_migrations() -> None:
    """Add any columns missing from an older database (forward-only)."""
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            for name, ddl_type in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"
                    )


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
