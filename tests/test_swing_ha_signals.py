"""Causality and lifecycle contracts for the Swing/HA challenger."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.swing_ha_signals import (
    SwingHaSignalConfig,
    build_heikin_ashi,
    build_swing_ha_signals,
    confirmed_pivot_levels,
)


def _bars(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(opens), freq="15min", tz="UTC")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes},
        index=index,
    )


def test_heikin_ashi_uses_recursive_open_and_never_changes_raw_prices() -> None:
    bars = _bars(
        [10.0, 12.0, 11.0],
        [13.0, 14.0, 13.0],
        [9.0, 10.0, 9.0],
        [12.0, 11.0, 12.0],
    )

    result = build_heikin_ashi(bars)

    assert result["ha_close"].tolist() == pytest.approx([11.0, 11.75, 11.25])
    assert result["ha_open"].iloc[0] == pytest.approx(11.0)
    assert result["ha_open"].iloc[1] == pytest.approx(11.0)
    assert result["ha_open"].iloc[2] == pytest.approx(11.375)
    assert bars["open"].tolist() == [10.0, 12.0, 11.0]


def test_pivot_is_unavailable_until_right_window_completes() -> None:
    bars = _bars(
        [1.0] * 9,
        [1.0, 2.0, 3.0, 5.0, 9.0, 6.0, 4.0, 3.0, 2.0],
        [0.5] * 9,
        [1.0] * 9,
    )

    levels = confirmed_pivot_levels(bars, pivot_length=2)

    assert levels["last_pivot_high"].iloc[:6].isna().all()
    assert levels["last_pivot_high"].iloc[6] == pytest.approx(9.0)
    assert levels["pivot_high_source_position"].iloc[6] == pytest.approx(4.0)


def test_appending_future_bars_does_not_change_prior_signal_rows() -> None:
    base = _bars(
        [10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22],
        [9, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
    )
    extension = _bars(
        [10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 19, 18],
        [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 20, 19],
        [9, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 18, 17],
        [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 19, 18],
    )
    config = SwingHaSignalConfig(fast_ema=3, slow_ema=5, pivot_length=2)

    before = build_swing_ha_signals(base, config)
    after = build_swing_ha_signals(extension, config).iloc[: len(base)]

    pd.testing.assert_frame_equal(before, after)


def test_repeated_alignment_state_becomes_one_shot_onset_when_requested() -> None:
    bars = _bars(
        [10, 9, 8, 9, 8.5, 10, 11, 12, 13, 14, 15],
        [11, 10, 9, 10, 9, 11, 12, 13, 14, 15, 16],
        [9, 8, 7, 8, 8, 9.5, 10, 11, 12, 13, 14],
        [9, 8, 7.5, 9.5, 8.8, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5],
    )
    state = build_swing_ha_signals(
        bars,
        SwingHaSignalConfig(
            fast_ema=2,
            slow_ema=3,
            pivot_length=1,
            entry_mode="state",
        ),
    )
    onset = build_swing_ha_signals(
        bars,
        SwingHaSignalConfig(
            fast_ema=2,
            slow_ema=3,
            pivot_length=1,
            entry_mode="onset",
        ),
    )

    assert state["long_entry"].sum() > onset["long_entry"].sum()
    assert onset["long_entry"].sum() == 1


def test_color_flip_exit_holds_doji_and_exits_on_opposite_color() -> None:
    bars = _bars(
        [10, 9, 8, 9, 10, 11, 12, 13, 13, 11],
        [11, 10, 9, 10, 11, 12, 13, 14, 13, 12],
        [9, 8, 7, 8, 9, 10, 11, 12, 13, 9],
        [9, 8, 7.5, 9.5, 10.5, 11.5, 12.5, 13.5, 13, 10],
    )
    signals = build_swing_ha_signals(
        bars,
        SwingHaSignalConfig(
            fast_ema=2,
            slow_ema=3,
            pivot_length=1,
            exit_mode="ha_flip",
        ),
    )

    red = signals["ha_color"].eq(-1)
    green = signals["ha_color"].eq(1)
    doji = signals["ha_color"].eq(0)
    assert signals.loc[red, "long_exit"].all()
    assert signals.loc[green, "short_exit"].all()
    assert not signals.loc[doji, ["long_exit", "short_exit"]].any().any()


def test_invalid_config_rejects_nonordered_emas() -> None:
    with pytest.raises(ValueError, match="fast_ema must be below slow_ema"):
        SwingHaSignalConfig(fast_ema=21, slow_ema=9)


def test_nonfinite_ohlc_fails_closed() -> None:
    bars = _bars([10, 11], [11, 12], [9, 10], [10, np.nan])

    with pytest.raises(ValueError, match="finite positive"):
        build_heikin_ashi(bars)
