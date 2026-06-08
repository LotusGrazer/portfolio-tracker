"""Forward-only schema migrations for pre-existing databases."""
import database as db


def _columns(table):
    with db.engine.begin() as conn:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}


def test_apply_migrations_adds_missing_column():
    # Simulate an older DB whose holdings table predates cost_currency.
    with db.engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE portfolio_holdings")
        conn.exec_driver_sql(
            "CREATE TABLE portfolio_holdings (id INTEGER PRIMARY KEY, ticker VARCHAR)"
        )
    assert "cost_currency" not in _columns("portfolio_holdings")

    db._apply_migrations()
    assert "cost_currency" in _columns("portfolio_holdings")


def test_apply_migrations_is_idempotent():
    before = _columns("portfolio_holdings")
    db._apply_migrations()
    db._apply_migrations()
    assert _columns("portfolio_holdings") == before
