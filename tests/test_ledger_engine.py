"""Pure FIFO engine: parcels, realised gains, CGT eligibility, fees."""
import datetime as dt

import pytest

from ledger import (
    BUY,
    SELL,
    Leg,
    financial_year_of,
    fifo_process,
)
from portfolio import PortfolioError


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def test_buy_then_full_sell_realises_gain():
    legs = [
        Leg(BUY, 100, 2.00, d("2023-01-01")),
        Leg(SELL, 100, 3.00, d("2023-06-01")),
    ]
    realised, parcels = fifo_process("AOV", legs)
    assert parcels == []
    assert len(realised) == 1
    e = realised[0]
    assert e.cost_base == 200.0
    assert e.proceeds == 300.0
    assert e.gain == 100.0


def test_partial_sell_leaves_open_parcel():
    legs = [
        Leg(BUY, 100, 2.00, d("2023-01-01")),
        Leg(SELL, 40, 3.00, d("2023-06-01")),
    ]
    realised, parcels = fifo_process("AOV", legs)
    assert realised[0].quantity == 40
    assert realised[0].gain == pytest.approx(40 * (3.0 - 2.0))
    assert len(parcels) == 1
    assert parcels[0].quantity == 60
    assert parcels[0].cost_base == pytest.approx(120.0)


def test_fifo_consumes_oldest_parcel_first():
    legs = [
        Leg(BUY, 100, 2.00, d("2023-01-01")),  # oldest, cost 2.00
        Leg(BUY, 100, 5.00, d("2023-03-01")),  # newer, cost 5.00
        Leg(SELL, 150, 6.00, d("2023-09-01")),
    ]
    realised, parcels = fifo_process("AOV", legs)
    # 100 from the $2 parcel, then 50 from the $5 parcel.
    assert [r.quantity for r in realised] == [100, 50]
    assert [r.cost_base for r in realised] == [200.0, 250.0]
    assert realised[0].gain == pytest.approx(100 * (6 - 2))
    assert realised[1].gain == pytest.approx(50 * (6 - 5))
    # 50 of the $5 parcel remains.
    assert len(parcels) == 1
    assert parcels[0].quantity == 50
    assert parcels[0].price_per_unit == 5.00


def test_cgt_discount_eligibility_by_holding_period():
    # Held > 12 months -> eligible.
    long_hold = fifo_process(
        "X",
        [Leg(BUY, 1, 1.0, d("2022-01-01")), Leg(SELL, 1, 2.0, d("2023-06-01"))],
    )[0][0]
    assert long_hold.cgt_discount_eligible is True

    # Held <= 12 months -> not eligible.
    short_hold = fifo_process(
        "X",
        [Leg(BUY, 1, 1.0, d("2023-01-01")), Leg(SELL, 1, 2.0, d("2023-06-01"))],
    )[0][0]
    assert short_hold.cgt_discount_eligible is False


def test_exactly_365_days_is_not_eligible():
    # Boundary: must be held *more* than 12 months.
    e = fifo_process(
        "X",
        [Leg(BUY, 1, 1.0, d("2023-01-01")), Leg(SELL, 1, 2.0, d("2024-01-01"))],
    )[0][0]
    assert (e.sell_date - e.buy_date).days == 365
    assert e.cgt_discount_eligible is False


def test_oversell_raises():
    legs = [
        Leg(BUY, 50, 2.00, d("2023-01-01")),
        Leg(SELL, 80, 3.00, d("2023-06-01")),
    ]
    with pytest.raises(PortfolioError, match="oversell"):
        fifo_process("AOV", legs)


def test_fees_increase_cost_and_reduce_proceeds():
    # Buy fee 10 over 100 units -> +0.10/unit cost. Sell fee 20 over 100 -> -0.20/unit proceeds.
    legs = [
        Leg(BUY, 100, 2.00, d("2023-01-01"), fee=10.0),
        Leg(SELL, 100, 3.00, d("2023-06-01"), fee=20.0),
    ]
    e = fifo_process("AOV", legs)[0][0]
    assert e.cost_base == pytest.approx(210.0)  # 100*2 + 10
    assert e.proceeds == pytest.approx(280.0)  # 100*3 - 20
    assert e.gain == pytest.approx(70.0)


def test_legs_sorted_by_date_regardless_of_input_order():
    legs = [
        Leg(SELL, 100, 3.00, d("2023-06-01")),  # listed first but later date
        Leg(BUY, 100, 2.00, d("2023-01-01")),
    ]
    realised, parcels = fifo_process("AOV", legs)
    assert realised[0].gain == 100.0
    assert parcels == []


@pytest.mark.parametrize(
    "date_str,expected",
    [
        ("2023-07-01", "2023-24"),  # first day of FY
        ("2024-06-30", "2023-24"),  # last day of FY
        ("2024-07-01", "2024-25"),
        ("2024-03-15", "2023-24"),
    ],
)
def test_financial_year_of(date_str, expected):
    assert financial_year_of(d(date_str)) == expected
