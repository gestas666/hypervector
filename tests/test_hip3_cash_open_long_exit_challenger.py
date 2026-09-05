"""Tests for the preregistered SPCX long exit challenger."""

from __future__ import annotations

import pytest

from hypervector.research.hip3_cash_open_long_exit_challenger import (
    evaluate_cash_open_long_exit_challengers,
)
from hip3_cash_open_gap_reversal_fixtures import archive_bars, execution


def test_fixed_targets_share_control_entries_and_anchor_to_fills() -> None:
    """Change only the long target and preserve exact entry identity."""
    bars, windows = archive_bars()

    result = evaluate_cash_open_long_exit_challengers(
        bars,
        execution("xyz:SPCX"),
        windows=windows,
        target_bps=(40.0, 60.0, 80.0),
    )

    control = result.control.development.nominal.trades
    assert len(control) == 1
    assert control[0].direction == "long"
    assert control[0].target_price == pytest.approx(100.0)
    control_entries = [(trade.signal_time_utc, trade.entry_price) for trade in control]
    for target_bps, scenario in zip((40.0, 60.0, 80.0), result.challengers):
        trades = scenario.development.nominal.trades
        assert [(trade.signal_time_utc, trade.entry_price) for trade in trades] == (
            control_entries
        )
        expected_target = trades[0].entry_price * (1.0 + target_bps / 10_000.0)
        assert trades[0].target_price == pytest.approx(expected_target)
        assert scenario.target_bps == target_bps
    assert result.validation_accessed is False
    assert result.holdout_accessed is False
    assert result.execution_authority == "none"


def test_challenger_rejects_duplicate_or_nonpositive_targets() -> None:
    """Require a small, explicit, unique positive candidate family."""
    bars, windows = archive_bars()
    with pytest.raises(ValueError, match="unique positive"):
        evaluate_cash_open_long_exit_challengers(
            bars,
            execution("xyz:SPCX"),
            windows=windows,
            target_bps=(40.0, 40.0),
        )
    with pytest.raises(ValueError, match="unique positive"):
        evaluate_cash_open_long_exit_challengers(
            bars,
            execution("xyz:SPCX"),
            windows=windows,
            target_bps=(0.0,),
        )
