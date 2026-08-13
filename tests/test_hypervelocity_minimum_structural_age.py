"""Tests for the report-only minimum structural age challenger."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_regime_entry_minimum_age,
)


def _decisions() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=9, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "state_5m": [
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "TREND_UP",
                "RANGE",
                "TREND_DOWN",
                "TREND_DOWN",
            ],
            "structural_direction": [
                "long",
                "long",
                "long",
                "long",
                "long",
                "long",
                None,
                "short",
                "short",
            ],
            "entry_direction": [
                "long",
                "long",
                "long",
                "long",
                "long",
                "long",
                None,
                "short",
                "short",
            ],
        },
        index=index,
    )


def test_minimum_age_blocks_audit_ages_below_five_only() -> None:
    """Five prior same-state decisions must elapse before entry eligibility."""
    decisions = _decisions()

    result = apply_regime_entry_minimum_age(
        decisions,
        minimum_age_inclusive=5,
    )

    assert result["regime_age_5m_bars"].tolist() == [0, 1, 2, 3, 4, 5, 0, 0, 1]
    assert result["regime_entry_minimum_age_blocked"].tolist() == [
        True,
        True,
        True,
        True,
        True,
        False,
        False,
        True,
        True,
    ]
    assert result["entry_direction"].iloc[:5].isna().all()
    assert result["entry_direction"].iloc[5] == "long"


def test_minimum_age_is_causal_and_preserves_canonical_structure() -> None:
    """A future state change cannot rewrite earlier challenger decisions."""
    decisions = _decisions()

    result = apply_regime_entry_minimum_age(decisions, minimum_age_inclusive=5)
    prefix = apply_regime_entry_minimum_age(
        decisions.iloc[:7],
        minimum_age_inclusive=5,
    )

    assert result["state_5m"].tolist() == decisions["state_5m"].tolist()
    assert (
        result["structural_direction"].tolist()
        == decisions["structural_direction"].tolist()
    )
    pd.testing.assert_frame_equal(result.iloc[:7], prefix)


@pytest.mark.parametrize("minimum_age", [0, -1, True, 1.5])
def test_minimum_age_rejects_invalid_boundaries(minimum_age: object) -> None:
    decisions = _decisions()

    with pytest.raises(ValueError, match="minimum_age_inclusive"):
        apply_regime_entry_minimum_age(
            decisions,
            minimum_age_inclusive=minimum_age,  # type: ignore[arg-type]
        )
