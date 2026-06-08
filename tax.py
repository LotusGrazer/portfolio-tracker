"""Australian resident income-tax estimate, used to put a tax figure on a
realised capital gain.

A net capital gain is added to assessable income and taxed at marginal rates,
so the tax *attributable to a gain* is best computed marginally:

    tax(income + net_gain) - tax(income)

This module is pure (no DB/framework) and financial-year aware, because the
resident brackets changed from 1 July 2024 ("stage 3").

Heavy caveats — this is an informational estimate, not tax advice:
  * Resident rates only; ignores offsets (e.g. LITO), HELP/HECS, the Medicare
    levy surcharge, and family/low-income Medicare adjustments.
  * Treats the portfolio as a single tax entity (no household/partner split).
  * Uses a flat 2% Medicare levy above a single threshold (no shade-in).

FUTURE: the 50% CGT discount is expected to be replaced by an inflation
(indexation) method. When that lands, the discount logic in ledger.py and the
"net capital gain" fed in here will need a new path; this marginal-tax step
stays the same.
"""
from __future__ import annotations

import math

# (lower_exclusive, upper_inclusive, marginal_rate)
_STAGE3 = [  # 2024-25 onwards
    (0, 18_200, 0.0),
    (18_200, 45_000, 0.16),
    (45_000, 135_000, 0.30),
    (135_000, 190_000, 0.37),
    (190_000, math.inf, 0.45),
]
_STAGE2 = [  # 2023-24 and earlier
    (0, 18_200, 0.0),
    (18_200, 45_000, 0.19),
    (45_000, 120_000, 0.325),
    (120_000, 180_000, 0.37),
    (180_000, math.inf, 0.45),
]

MEDICARE_LEVY = 0.02
MEDICARE_THRESHOLD = 27_222  # single, 2024-25 (simplified, no shade-in)


def _fy_ending_year(financial_year: str | None) -> int | None:
    """Ending calendar year of an FY label, e.g. "2024-25" -> 2025."""
    if not financial_year:
        return None
    try:
        return int(financial_year.split("-")[0]) + 1
    except (ValueError, AttributeError):
        return None


def brackets_for(financial_year: str | None) -> list[tuple[float, float, float]]:
    """Resident brackets for an FY (defaults to the current/stage-3 schedule)."""
    ending = _fy_ending_year(financial_year)
    if ending is not None and ending <= 2024:
        return _STAGE2
    return _STAGE3


def income_tax(income: float, financial_year: str | None = None) -> float:
    """Progressive resident income tax (excludes Medicare levy)."""
    if income <= 0:
        return 0.0
    tax = 0.0
    for lower, upper, rate in brackets_for(financial_year):
        if income > lower:
            tax += (min(income, upper) - lower) * rate
        else:
            break
    return tax


def medicare_levy(income: float) -> float:
    return income * MEDICARE_LEVY if income > MEDICARE_THRESHOLD else 0.0


def _total_tax(income: float, financial_year: str | None) -> float:
    return income_tax(income, financial_year) + medicare_levy(income)


def estimate_tax_on_gain(
    taxable_income: float,
    net_capital_gain: float,
    financial_year: str | None = None,
) -> dict:
    """Estimate the extra tax a net capital gain attracts at the margin.

    A capital loss (net_capital_gain <= 0) attracts no tax here (we don't model
    loss carry-forward). Returns the additional tax and the effective rate on
    the gain.
    """
    income = max(taxable_income, 0.0)
    if net_capital_gain <= 0:
        return {
            "taxable_income": round(income, 2),
            "financial_year_basis": financial_year or "current (assumed)",
            "additional_tax": 0.0,
            "effective_rate_on_gain_pct": 0.0,
        }
    additional = _total_tax(income + net_capital_gain, financial_year) - _total_tax(
        income, financial_year
    )
    return {
        "taxable_income": round(income, 2),
        "financial_year_basis": financial_year or "current (assumed)",
        "additional_tax": round(additional, 2),
        "effective_rate_on_gain_pct": round(additional / net_capital_gain * 100, 2),
    }
