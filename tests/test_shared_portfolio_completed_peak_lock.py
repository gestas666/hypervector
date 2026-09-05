"""Unit tests for the completed-close graduated peak lock."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.shared_portfolio_completed_peak_lock import (
    CompletedBarPeakLockPolicy,
    completed_close_peak_lock_triggered,
)


def _bars(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value + 10.0 for value in closes],
            "low": [value - 10.0 for value in closes],
            "close": closes,
        },
        index=index,
    )


@pytest.mark.parametrize(
    ("direction", "closes"),
    [
        ("long", [100.5, 100.4]),
        ("short", [99.5, 99.6]),
    ],
)
def test_lock_uses_completed_close_roe_for_both_sides(
    direction: str,
    closes: list[float],
) -> None:
    """A 2.5% ROE peak at 5x locks 85% and triggers on a 2% close."""
    bars = _bars(closes)
    policy = CompletedBarPeakLockPolicy("gate_2pct_lock85", 2.0, 0.85)

    assert not completed_close_peak_lock_triggered(
        bars,
        entry_position=0,
        current_position=0,
        direction=direction,
        entry_price=100.0,
        leverage=5.0,
        policy=policy,
    )
    assert completed_close_peak_lock_triggered(
        bars,
        entry_position=0,
        current_position=1,
        direction=direction,
        entry_price=100.0,
        leverage=5.0,
        policy=policy,
    )


def test_lock_ignores_high_low_and_is_append_invariant() -> None:
    """Only the supplied completed-close prefix can affect a lock decision."""
    bars = _bars([100.0, 99.9, 140.0])
    policy = CompletedBarPeakLockPolicy("gate_2pct_lock85", 2.0, 0.85)

    assert not completed_close_peak_lock_triggered(
        bars,
        entry_position=0,
        current_position=1,
        direction="long",
        entry_price=100.0,
        leverage=5.0,
        policy=policy,
    )


@pytest.mark.parametrize(
    ("activation", "ratio"),
    [(0.0, 0.85), (2.0, 0.0), (2.0, 1.0), (2.0, 1.1)],
)
def test_policy_rejects_invalid_values(activation: float, ratio: float) -> None:
    """The graduated lock declaration must be finite and bounded."""
    with pytest.raises(ValueError):
        CompletedBarPeakLockPolicy("invalid", activation, ratio)
