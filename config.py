"""Application configuration.

All values can be overridden with environment variables, which keeps secrets and
machine-specific paths out of the codebase. Sensible defaults are provided so the
app runs out of the box for local use.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# SQLite lives in the project root by default (see DATABASE_URL).
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'portfolio.db')}"
)

# The currency every value in /portfolio/summary is reported in. The portfolio
# holds a mix of AUD (ASX) and USD (US/crypto) instruments, so we normalise to a
# single base currency for totals. Australian household -> AUD by default.
BASE_CURRENCY = os.environ.get("BASE_CURRENCY", "AUD")

# How long a cached price/FX rate is considered fresh before we re-query
# yfinance. Keeps us from hammering Yahoo on every API call.
PRICE_CACHE_TTL_MINUTES = int(os.environ.get("PRICE_CACHE_TTL_MINUTES", "15"))

# Holdings uploaded without an explicit portfolio name land here.
DEFAULT_PORTFOLIO = os.environ.get("DEFAULT_PORTFOLIO", "My Portfolio")
