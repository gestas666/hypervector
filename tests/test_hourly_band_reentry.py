"""Causality and symmetric recovery tests for the hourly reversion hypothesis."""

import numpy as np
import pandas as pd

from hypervector.research.hourly_band_reentry import build_hourly_band_reentry_signals


def _bars() -> pd.DataFrame:
    hourly = [100.0] * 25 + [90.0, 97.0, 100.0, 110.0, 103.0, 100.0]
    values = np.repeat(hourly, 4)
    return pd.DataFrame(
        {"open": values, "high": values + 0.5, "low": values - 0.5, "close": values},
        index=pd.date_range("2026-01-01", periods=len(values), freq="15min", tz="UTC"),
    )


def test_reentry_waits_for_recovery_and_emits_symmetric_completed_hour_entries() -> (
    None
):
    """An excursion itself does not enter; a later completed recovery does."""
    bars = _bars()
    result = build_hourly_band_reentry_signals(bars)
    assert result.index[result.long_entry].tolist() == [bars.index[26 * 4 + 3]]
    assert result.index[result.short_entry].tolist() == [bars.index[29 * 4 + 3]]
    assert result.loc[bars.index[26 * 4 + 3], "stop_price"] < 97.0
    assert result.loc[bars.index[29 * 4 + 3], "stop_price"] > 103.0
    assert result.loc[bars.index[27 * 4 + 3], "long_exit"]
    assert result.loc[bars.index[30 * 4 + 3], "short_exit"]


def test_future_and_incomplete_hour_do_not_rewrite_decisions() -> None:
    """Every truncated input must match the corresponding full-result prefix."""
    bars = _bars()
    full = build_hourly_band_reentry_signals(bars)
    for count in (102, 103, 104, 107, 108, 119, 120):
        prefix = build_hourly_band_reentry_signals(bars.iloc[:count])
        pd.testing.assert_frame_equal(prefix, full.iloc[:count])


def test_gap_discards_pre_gap_band_and_volatility_state() -> None:
    """A missing quarter-hour before recovery makes the old band unavailable."""
    bars = _bars().drop(_bars().index[24 * 4])
    result = build_hourly_band_reentry_signals(bars)
    assert not result.long_entry.any()
    assert not result.short_entry.any()
