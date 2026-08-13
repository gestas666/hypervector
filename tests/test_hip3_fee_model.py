"""Tests for official-formula HIP-3 fee sensitivities."""

from __future__ import annotations

import pytest

from hypervector.research.hip3_fee_model import (
    Hip3FeeInputs,
    effective_hip3_fees,
)


def test_growth_mode_fee_formula_matches_observed_spcx_inputs() -> None:
    """Positive maker and taker rates must follow the documented HIP-3 scales."""
    fees = effective_hip3_fees(
        Hip3FeeInputs(
            account_maker_rate=0.00015,
            account_taker_rate=0.00045,
            active_referral_discount=0.04,
            deployer_fee_scale=1.0,
            growth_mode=True,
            aligned_quote=False,
            aligned_quote_status="unresolved_conservative_false",
            evidence_label="spcx-current-account-and-qualification",
        )
    )

    assert fees.effective_maker_rate == pytest.approx(0.0000288)
    assert fees.effective_taker_rate == pytest.approx(0.0000864)
    assert fees.one_way_maker_fee_bps == pytest.approx(0.288)
    assert fees.one_way_taker_fee_bps == pytest.approx(0.864)
    assert fees.round_trip_taker_fee_bps == pytest.approx(1.728)


def test_aligned_quote_reduces_positive_taker_but_not_positive_maker() -> None:
    """Aligned collateral affects taker fees under the official formula."""
    base = Hip3FeeInputs(
        account_maker_rate=0.00015,
        account_taker_rate=0.00045,
        active_referral_discount=0.0,
        deployer_fee_scale=1.0,
        growth_mode=False,
        aligned_quote=True,
        aligned_quote_status="verified_true",
        evidence_label="fixture",
    )

    fees = effective_hip3_fees(base)

    assert fees.effective_maker_rate == pytest.approx(0.00030)
    assert fees.effective_taker_rate == pytest.approx(0.00081)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("active_referral_discount", 1.0),
        ("deployer_fee_scale", 3.1),
        ("account_taker_rate", -0.1),
    ],
)
def test_fee_inputs_reject_invalid_contract(field: str, value: float) -> None:
    """Invalid fee evidence must fail before producing cost estimates."""
    values: dict[str, object] = {
        "account_maker_rate": 0.00015,
        "account_taker_rate": 0.00045,
        "active_referral_discount": 0.0,
        "deployer_fee_scale": 1.0,
        "growth_mode": True,
        "aligned_quote": False,
        "aligned_quote_status": "unresolved_conservative_false",
        "evidence_label": "fixture",
    }
    values[field] = value

    with pytest.raises(ValueError, match=field):
        Hip3FeeInputs(**values)  # type: ignore[arg-type]
