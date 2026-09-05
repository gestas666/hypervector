"""Causal tests for the slower SMA/ATR trend candidate."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.sma_atr_trend_signals import (
    SmaAtrTrendConfig,
    build_sma_atr_trend_signals,
    build_sma_atr_trend_state,
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
    rows: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []
    for timestamp, row in _signal_bars(closes).iterrows():
        for offset in range(16):
            index.append(timestamp + pd.Timedelta(minutes=15 * offset))
            rows.append({column: float(row[column]) for column in row.index})
    return pd.DataFrame.from_records(rows, index=pd.DatetimeIndex(index))


def _config() -> SmaAtrTrendConfig:
    return SmaAtrTrendConfig(fast_period=2, slow_period=3, atr_period=2)


def test_state_emits_fresh_crosses_with_atr_structural_stops() -> None:
    """Only new trend-state crosses may enter, each with a causal ATR stop."""
    bars = _signal_bars([3, 2, 1, 2, 3, 2, 1])

    state = build_sma_atr_trend_state(bars, _config())

    assert state.index[state["long_entry"]].tolist() == [bars.index[4]]
    assert state.index[state["short_entry"]].tolist() == [bars.index[6]]
    assert state.loc[bars.index[4], "stop_price"] < bars["close"].iloc[4]
    assert state.loc[bars.index[6], "stop_price"] > bars["close"].iloc[6]


def test_completed_cross_maps_to_last_15m_decision_row() -> None:
    """The engine can fill a cross only at the next observed 15m open."""
    bars = _execution_bars([3, 2, 1, 2, 3, 2, 1])

    signals = build_sma_atr_trend_signals(bars, _config())

    assert signals.index[signals["long_entry"]].tolist() == [
        pd.Timestamp("2026-01-01T19:45:00Z")
    ]
    assert signals.index[signals["short_entry"]].tolist() == [
        pd.Timestamp("2026-01-02T03:45:00Z")
    ]
    assert signals.loc["2026-01-01T19:45:00Z", "short_exit"]
    assert signals.loc["2026-01-02T03:45:00Z", "long_exit"]


def test_future_suffix_cannot_change_prior_crosses_or_stops() -> None:
    """Appending extreme future bars must preserve the completed prefix."""
    prefix = _execution_bars([3, 2, 1, 2, 3, 2, 1, 2])
    suffix = _execution_bars([50, 1, 80])
    suffix.index = pd.date_range(
        prefix.index[-1] + pd.Timedelta(minutes=15),
        periods=len(suffix),
        freq="15min",
        tz="UTC",
    )

    expected = build_sma_atr_trend_signals(prefix, _config())
    actual = build_sma_atr_trend_signals(pd.concat([prefix, suffix]), _config())

    pd.testing.assert_frame_equal(actual.loc[prefix.index], expected)


def test_gap_resets_sma_and_atr_warmup() -> None:
    """Unknown bars must break both moving-average and ATR state."""
    bars = _execution_bars([3, 2, 1, 2, 3, 2, 1, 2])
    bars = bars.drop(pd.Timestamp("2026-01-01T16:00:00Z"))

    signals = build_sma_atr_trend_signals(bars, _config())

    after_gap = signals.loc["2026-01-01T16:00:00Z":]
    assert not after_gap["long_entry"].any()
    assert not after_gap["short_entry"].any()


@pytest.mark.parametrize(
    "overrides",
    [
        {"fast_period": 0},
        {"fast_period": 30, "slow_period": 10},
        {"atr_period": 0},
        {"atr_multiple": 0.0},
        {"signal_hours": 1},
        {"execution_minutes": 5},
    ],
)
def test_config_rejects_incoherent_values(
    overrides: dict[str, float | int],
) -> None:
    """Malformed strategy values must fail before any result is computed."""
    with pytest.raises(ValueError):
        SmaAtrTrendConfig(**overrides)
