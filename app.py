"""Flask application exposing the portfolio tracker REST API.

Run locally:
    python app.py
or:
    flask --app app run --debug
"""
from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS

import portfolio as pf
from database import init_db, session_scope


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)  # allow the Phase 2 React frontend to call us cross-origin
    init_db()

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
    app.run(host="127.0.0.1", port=5000, debug=True)
