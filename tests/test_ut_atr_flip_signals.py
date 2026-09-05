"""Causal tests for the independently implemented UT/ATR signal family."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.ut_atr_flip_signals import (
    UtAtrFlipConfig,
    build_ut_atr_flip_signals,
    build_ut_atr_flip_state,
)


def _four_hour_bars(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="4h", tz="UTC")
    values = np.asarray(closes, dtype=np.float64)
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 0.5,
            "low": values - 0.5,
            "close": values,
        },
        index=index,
    )


def _fifteen_minute_bars(closes: list[float]) -> pd.DataFrame:
    four_hour = _four_hour_bars(closes)
    records: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []
    for timestamp, row in four_hour.iterrows():
        for offset in range(16):
            index.append(timestamp + pd.Timedelta(minutes=15 * offset))
            records.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )
    return pd.DataFrame.from_records(records, index=pd.DatetimeIndex(index))


def test_state_uses_raw_true_range_and_ohlc_mean_source() -> None:
    """Variant R must not compute ATR from synthetic Heikin-Ashi bars."""
    bars = _four_hour_bars([10.0, 11.0, 12.0])
    bars.loc[bars.index[0], ["open", "high", "low", "close"]] = [8, 14, 7, 11]

    state = build_ut_atr_flip_state(bars, UtAtrFlipConfig(atr_period=2))

    assert state["signal_source"].iloc[0] == pytest.approx(10.0)
    assert state["true_range"].iloc[0] == pytest.approx(7.0)
    assert state["atr"].iloc[1] == pytest.approx(4.0)


def test_state_emits_only_crossing_flips_with_native_stops() -> None:
    """The recurrence must emit one short flip and the later long flip."""
    bars = _four_hour_bars([10.0, 11.0, 12.0, 8.0, 7.0, 13.0])

    state = build_ut_atr_flip_state(bars, UtAtrFlipConfig(atr_period=2))

    assert state.index[state["short_entry"]].tolist() == [bars.index[3]]
    assert state.index[state["long_entry"]].tolist() == [bars.index[5]]
    assert state.loc[bars.index[3], "trailing_stop"] == pytest.approx(10.9375)
    assert state.loc[bars.index[5], "trailing_stop"] == pytest.approx(8.640625)


def test_completed_four_hour_decision_maps_to_last_fifteen_minute_bar() -> None:
    """A 4h close decision becomes eligible for exactly the next 15m open."""
    bars = _fifteen_minute_bars([10.0, 11.0, 12.0, 8.0, 7.0, 13.0])

    signals = build_ut_atr_flip_signals(bars, UtAtrFlipConfig(atr_period=2))

    short_at = pd.Timestamp("2026-01-01T15:45:00Z")
    long_at = pd.Timestamp("2026-01-01T23:45:00Z")
    assert signals.index[signals["short_entry"]].tolist() == [short_at]
    assert signals.index[signals["long_entry"]].tolist() == [long_at]
    assert signals.loc[short_at, "long_exit"]
    assert signals.loc[long_at, "short_exit"]
    assert signals.loc[short_at, "stop_price"] == pytest.approx(10.9375)


def test_future_suffix_cannot_change_prior_signals_or_stops() -> None:
    """Appending or mutating future bars must leave the causal prefix unchanged."""
    prefix = _fifteen_minute_bars([10, 11, 12, 8, 7, 13, 14, 15])
    suffix = _fifteen_minute_bars([16, 12, 18, 9])
    suffix.index = pd.date_range(
        prefix.index[-1] + pd.Timedelta(minutes=15),
        periods=len(suffix),
        freq="15min",
        tz="UTC",
    )
    changed = suffix.copy()
    changed.loc[:, ["open", "high", "low", "close"]] *= 4.0

    expected = build_ut_atr_flip_signals(prefix, UtAtrFlipConfig(atr_period=2))
    actual = build_ut_atr_flip_signals(
        pd.concat([prefix, changed]),
        UtAtrFlipConfig(atr_period=2),
    ).loc[prefix.index]

    pd.testing.assert_frame_equal(actual, expected)


def test_gap_resets_atr_and_stop_state() -> None:
    """A missing execution bar must prevent indicators bridging unknown prices."""
    bars = _fifteen_minute_bars([10, 11, 12, 8, 7, 13, 14, 15])
    bars = bars.drop(pd.Timestamp("2026-01-01T16:00:00Z"))

    signals = build_ut_atr_flip_signals(bars, UtAtrFlipConfig(atr_period=2))

    after_gap = signals.loc["2026-01-01T16:00:00Z":]
    assert not after_gap["long_entry"].any()
    assert not after_gap["short_entry"].any()


@pytest.mark.parametrize(
    "overrides",
    [
        {"atr_period": 0},
        {"key_value": 0.0},
        {"signal_hours": 3},
        {"execution_minutes": 0},
    ],
)
def test_config_rejects_unsafe_or_incompatible_values(
    overrides: dict[str, float | int],
) -> None:
    """Configuration errors must fail before a backtest can look successful."""
    with pytest.raises(ValueError):
        UtAtrFlipConfig(**overrides)
