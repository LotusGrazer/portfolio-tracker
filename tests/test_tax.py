"""Australian resident income-tax estimate (FY-aware brackets + marginal gain)."""
import pytest

import tax


def test_income_tax_stage3_known_points():
    # 2024-25: tax-free to 18,200; 16% to 45,000; 30% to 135,000.
    assert tax.income_tax(18_200, "2024-25") == 0.0
    assert tax.income_tax(45_000, "2024-25") == pytest.approx(26_800 * 0.16)  # 4288
    # 4288 + (135000-45000)*0.30 = 31,288
    assert tax.income_tax(135_000, "2024-25") == pytest.approx(31_288)


def test_income_tax_stage2_for_earlier_fy():
    # 2023-24 used the 19% / 32.5% schedule.
    assert tax.income_tax(45_000, "2023-24") == pytest.approx(26_800 * 0.19)  # 5092


def test_brackets_switch_on_fy():
    assert tax.brackets_for("2023-24") is tax._STAGE2
    assert tax.brackets_for("2024-25") is tax._STAGE3
    assert tax.brackets_for(None) is tax._STAGE3  # defaults to current


def test_estimate_tax_on_gain_marginal():
    # Income 100k + 10k gain, all within the 30% bracket (2024-25): 30% + 2% MC.
    est = tax.estimate_tax_on_gain(100_000, 10_000, "2024-25")
    assert est["additional_tax"] == pytest.approx(3_200)  # 3000 income tax + 200 MC
    assert est["effective_rate_on_gain_pct"] == pytest.approx(32.0)


def test_estimate_tax_crosses_bracket():
    # Income 130k, gain 10k: 5k taxed at 30%, 5k at 37% (+2% MC across).
    est = tax.estimate_tax_on_gain(130_000, 10_000, "2024-25")
    expected = 5_000 * 0.30 + 5_000 * 0.37 + 10_000 * 0.02
    assert est["additional_tax"] == pytest.approx(expected)


def test_capital_loss_no_tax():
    est = tax.estimate_tax_on_gain(100_000, -5_000, "2024-25")
    assert est["additional_tax"] == 0.0
