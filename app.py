"""Flask application: portfolio tracker REST API + bundled frontend.

Run locally:
    python app.py            # serves API + built frontend at http://127.0.0.1:5000
    FLASK_DEBUG=1 python app.py   # dev: auto-reload

The built React app (frontend/dist) is served at the root, so the whole tool
runs as a single process at a single URL. During frontend development you can
still run the Vite dev server separately (npm run dev) — CORS is enabled.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

import config
import ledger
import portfolio as pf
from database import init_db, session_scope

FRONTEND_DIST = os.path.join(config.BASE_DIR, "frontend", "dist")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=FRONTEND_DIST, static_url_path="")
    CORS(app)  # allow a separate Vite dev server to call us cross-origin
    init_db()

    @app.get("/")
    def index():
        index_html = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_html):
            return send_file(index_html)
        return jsonify(
            {
                "message": "Frontend not built yet. Run setup.command (or "
                "`cd frontend && npm install && npm run build`), then reload.",
                "api": "ok",
            }
        )

    # --------------------------------------------------------------------- #
    # Error handling
    # --------------------------------------------------------------------- #
    @app.errorhandler(pf.PortfolioError)
    def _handle_portfolio_error(exc: pf.PortfolioError):
        return jsonify({"error": str(exc)}), 400

    @app.errorhandler(404)
    def _handle_404(_exc):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        app.logger.exception("Unexpected error")
        return jsonify({"error": "internal server error", "detail": str(exc)}), 500

    # --------------------------------------------------------------------- #
    # Routes
    # --------------------------------------------------------------------- #
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/holdings")
    def get_holdings():
        with session_scope() as session:
            return jsonify(pf.get_actual_holdings(session))

    @app.post("/holdings/upload")
    def upload_holdings():
        raw, error = _read_csv_payload()
        if error:
            return jsonify({"error": error}), 400
        portfolio_name = request.form.get("portfolio") or request.args.get("portfolio")
        replace = _truthy(request.form.get("replace") or request.args.get("replace"))
        with session_scope() as session:
            result = pf.ingest_holdings_csv(
                session, raw, portfolio_name=portfolio_name, replace=replace
            )
        return jsonify(result.as_dict()), 201

    @app.get("/portfolio/summary")
    def get_summary():
        with session_scope() as session:
            return jsonify(pf.portfolio_summary(session))

    @app.get("/benchmarks")
    def get_benchmarks():
        with session_scope() as session:
            return jsonify(pf.list_benchmarks(session))

    @app.get("/benchmarks/compare")
    def compare_benchmarks():
        # ?periods=1mo,3mo,1y  (defaults applied if omitted/empty)
        raw_periods = request.args.get("periods")
        periods = None
        if raw_periods:
            requested = [p.strip() for p in raw_periods.split(",") if p.strip()]
            invalid = [p for p in requested if p not in pf.SUPPORTED_PERIODS]
            if invalid:
                return jsonify(
                    {
                        "error": f"unsupported period(s): {', '.join(invalid)}",
                        "supported": list(pf.SUPPORTED_PERIODS),
                    }
                ), 400
            periods = requested or None
        with session_scope() as session:
            return jsonify(pf.compare_to_benchmarks(session, periods))

    @app.post("/benchmarks/create")
    def create_benchmark():
        # Accept either a CSV upload or a JSON body.
        if request.is_json:
            with session_scope() as session:
                result = pf.create_benchmark_from_dict(session, request.get_json())
            return jsonify(result), 201

        raw, error = _read_csv_payload()
        if error:
            return jsonify({"error": error}), 400
        with session_scope() as session:
            result = pf.create_benchmark_from_csv(session, raw)
        return jsonify(result), 201

    # --------------------------------------------------------------------- #
    # Transactions / CGT (Phase 3)
    # --------------------------------------------------------------------- #
    @app.get("/transactions")
    def get_transactions():
        with session_scope() as session:
            return jsonify(ledger.get_transactions(session))

    @app.post("/transactions/upload")
    def upload_transactions():
        raw, error = _read_csv_payload()
        if error:
            return jsonify({"error": error}), 400
        portfolio_name = request.form.get("portfolio") or request.args.get("portfolio")
        replace = _truthy(request.form.get("replace") or request.args.get("replace"))
        with session_scope() as session:
            result = ledger.ingest_transactions_csv(
                session, raw, portfolio_name=portfolio_name, replace=replace
            )
        return jsonify(result.as_dict()), 201

    @app.get("/portfolio/realised")
    def get_realised():
        # ?financial_year=2023-24 (optional) &taxable_income=120000 (optional)
        fy = request.args.get("financial_year")
        income_raw = request.args.get("taxable_income")
        try:
            taxable_income = float(income_raw) if income_raw not in (None, "") else None
        except ValueError:
            return jsonify({"error": "taxable_income must be a number"}), 400
        with session_scope() as session:
            return jsonify(
                ledger.compute_realised(
                    session, financial_year=fy, taxable_income=taxable_income
                )
            )

    @app.post("/transactions/sync-holdings")
    def sync_holdings():
        # Rebuild holdings from the ledger's open (FIFO) parcels.
        portfolio_name = request.form.get("portfolio") or request.args.get("portfolio")
        with session_scope() as session:
            return jsonify(
                ledger.sync_holdings_from_transactions(session, portfolio_name)
            )

    return app


# ------------------------------------------------------------------------- #
# Request helpers
# ------------------------------------------------------------------------- #
def _read_csv_payload() -> tuple[bytes | None, str | None]:
    """Return raw CSV bytes from a multipart 'file' field or the raw body."""
    if "file" in request.files:
        return request.files["file"].read(), None
    if request.data:
        return request.data, None
    return None, "no CSV provided (upload a multipart 'file' or POST the raw CSV body)"


def _truthy(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"} if value else False


app = create_app()


if __name__ == "__main__":
    # Debug/reloader off by default so the launcher runs a single clean process;
    # set FLASK_DEBUG=1 for auto-reload during development.
    debug = _truthy(os.environ.get("FLASK_DEBUG"))
    app.run(host="127.0.0.1", port=5000, debug=debug)
