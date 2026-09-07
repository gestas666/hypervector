"""Check the new hourly cadence without changing the existing four-hour recipe."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from hypervector.research.donchian_atr_breakout_signals import (
    DonchianAtrBreakoutConfig,
    build_donchian_atr_breakout_signals,
)


def _bars() -> pd.DataFrame:
    values = np.repeat([10.0, 10.0, 10.0, 12.0, 13.0, 9.0, 8.0], 4)
    return pd.DataFrame(
        {"open": values, "high": values + 0.5, "low": values - 0.5, "close": values},
        index=pd.date_range("2026-01-01", periods=len(values), freq="15min", tz="UTC"),
    )


def _config() -> DonchianAtrBreakoutConfig:
    return DonchianAtrBreakoutConfig(
        entry_channel_bars=3,
        exit_channel_bars=2,
        atr_period=2,
        signal_hours=1,
    )


def test_hourly_signals_are_available_only_after_the_complete_hour() -> None:
    """The close-known long and short can execute at 04:00 and 06:00 only."""
    result = build_donchian_atr_breakout_signals(_bars(), _config())
    assert result.index[result.long_entry].tolist() == [
        pd.Timestamp("2026-01-01T03:45Z")
    ]
    assert result.index[result.short_entry].tolist() == [
        pd.Timestamp("2026-01-01T05:45Z")
    ]
    assert result.loc["2026-01-01T05:45Z", "long_exit"]
    assert result.signal_name.iloc[0] == "completed_1h_donchian_3_2_atr2_stop_v1"


def test_incomplete_hour_and_future_suffix_cannot_create_early_entries() -> None:
    """Quarter-hour prefixes must not see a later completed hourly breakout."""
    bars = _bars()
    full = build_donchian_atr_breakout_signals(bars, _config())
    for count in (14, 15, 16, 22, 23, 24):
        prefix = build_donchian_atr_breakout_signals(bars.iloc[:count], _config())
        pd.testing.assert_frame_equal(prefix, full.iloc[:count])


def test_hourly_source_gap_resets_channels_and_atr() -> None:
    """A missing quarter-hour cannot be bridged by the hourly indicators."""
    bars = _bars().drop(pd.Timestamp("2026-01-01T04:00Z"))
    signals = build_donchian_atr_breakout_signals(bars, _config())
    assert not signals.loc["2026-01-01T04:00Z":, "short_entry"].any()


@pytest.mark.parametrize("value", [True, 1.5, 0, 2])
def test_unsupported_hourly_clock_fails_explicitly(value: int | float) -> None:
    """Only the declared one-hour and existing four-hour clocks are supported."""
    with pytest.raises(ValueError):
        replace(_config(), signal_hours=value)
