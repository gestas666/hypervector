"""Causal tests for the Donchian/ATR breakout candidate."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.donchian_atr_breakout_signals import (
    DonchianAtrBreakoutConfig,
    build_donchian_atr_breakout_signals,
    build_donchian_atr_breakout_state,
)


def _signal_bars(closes: list[float]) -> pd.DataFrame:
    values = np.asarray(closes, dtype=np.float64)
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 0.5,
            "low": values - 0.5,
            "close": values,
        },
        index=pd.date_range("2026-01-01", periods=len(values), freq="4h", tz="UTC"),
    )


def _execution_bars(closes: list[float]) -> pd.DataFrame:
    records: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []
    for timestamp, row in _signal_bars(closes).iterrows():
        for offset in range(16):
            index.append(timestamp + pd.Timedelta(minutes=15 * offset))
            records.append({column: float(row[column]) for column in row.index})
    return pd.DataFrame.from_records(records, index=pd.DatetimeIndex(index))


def _config() -> DonchianAtrBreakoutConfig:
    return DonchianAtrBreakoutConfig(
        entry_channel_bars=3,
        exit_channel_bars=2,
        atr_period=2,
    )


def test_state_excludes_current_bar_and_emits_only_fresh_breakouts() -> None:
    """A new high enters once; the current high cannot suppress its own signal."""
    bars = _signal_bars([10, 10, 10, 12, 13, 9])

    state = build_donchian_atr_breakout_state(bars, _config())

    assert state.index[state["long_entry"]].tolist() == [bars.index[3]]
    assert state.index[state["short_entry"]].tolist() == [bars.index[5]]
    assert state.loc[bars.index[3], "prior_entry_high"] == pytest.approx(10.5)
    assert state.loc[bars.index[3], "stop_price"] < bars["close"].iloc[3]
    assert state.loc[bars.index[5], "stop_price"] > bars["close"].iloc[5]


def test_state_emits_side_specific_counter_channel_exits() -> None:
    """A 10-channel analogue exits the held side without inventing a target."""
    bars = _signal_bars([10, 10, 10, 12, 13, 9])

    state = build_donchian_atr_breakout_state(bars, _config())

    assert state.loc[bars.index[5], "long_exit"]
    assert not state.loc[bars.index[5], "short_exit"]


def test_completed_channel_decisions_map_to_last_fifteen_minute_row() -> None:
    """The engine can execute a completed 4h decision only at the next open."""
    bars = _execution_bars([10, 10, 10, 12, 13, 9])

    signals = build_donchian_atr_breakout_signals(bars, _config())

    long_at = pd.Timestamp("2026-01-01T15:45:00Z")
    short_at = pd.Timestamp("2026-01-01T23:45:00Z")
    assert signals.index[signals["long_entry"]].tolist() == [long_at]
    assert signals.index[signals["short_entry"]].tolist() == [short_at]
    assert signals.loc[short_at, "long_exit"]
    assert signals.loc[long_at, "prior_entry_high"] == pytest.approx(10.5)
    assert signals.loc[long_at, "atr"] > 0.0
    assert signals.loc[short_at, "prior_exit_low"] == pytest.approx(11.5)


def test_future_suffix_cannot_change_prior_entries_exits_or_stops() -> None:
    """Appending extreme future prices must preserve the completed prefix."""
    prefix = _execution_bars([10, 10, 10, 12, 13, 9, 8])
    suffix = _execution_bars([40, 2, 50])
    suffix.index = pd.date_range(
        prefix.index[-1] + pd.Timedelta(minutes=15),
        periods=len(suffix),
        freq="15min",
        tz="UTC",
    )

    expected = build_donchian_atr_breakout_signals(prefix, _config())
    actual = build_donchian_atr_breakout_signals(
        pd.concat([prefix, suffix]),
        _config(),
    )

    pd.testing.assert_frame_equal(actual.loc[prefix.index], expected)


def test_gap_resets_channels_and_atr_warmup() -> None:
    """Unknown execution bars must prevent channel state bridging a gap."""
    bars = _execution_bars([10, 10, 10, 12, 13, 9, 8])
    bars = bars.drop(pd.Timestamp("2026-01-01T16:00:00Z"))

    signals = build_donchian_atr_breakout_signals(bars, _config())

    after_gap = signals.loc["2026-01-01T16:00:00Z":]
    assert not after_gap["long_entry"].any()
    assert not after_gap["short_entry"].any()


@pytest.mark.parametrize(
    "overrides",
    [
        {"entry_channel_bars": 1},
        {"entry_channel_bars": 10, "exit_channel_bars": 10},
        {"atr_period": 0},
        {"atr_multiple": 0.0},
        {"signal_hours": 2},
        {"execution_minutes": 5},
    ],
)
def test_config_rejects_incoherent_values(
    overrides: dict[str, float | int],
) -> None:
    """Malformed channel or timing values must fail before replay."""
    with pytest.raises(ValueError):
        DonchianAtrBreakoutConfig(**overrides)
