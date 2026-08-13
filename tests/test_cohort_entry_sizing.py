"""Regression coverage for balance-independent cohort eligibility sizing."""

from __future__ import annotations

import pytest

from hypervector.live.cohort_entry_sizing import CohortEntrySizing


@pytest.mark.parametrize(
    ("account_value_usd", "expected_notional_usd"),
    ((50.0, 25.0), (500.0, 75.0), (5_000.0, 75.0)),
)
def test_positive_balance_is_not_a_five_hundred_dollar_gate(
    account_value_usd: float,
    expected_notional_usd: float,
) -> None:
    """Sizing responds continuously until its explicit order cap binds."""
    sizing = CohortEntrySizing(margin_fraction=0.10, max_notional_usd=75.0)

    planned = sizing.planned_notional(
        account_value_usd=account_value_usd,
        leverage=5.0,
    )

    assert planned == pytest.approx(expected_notional_usd)
