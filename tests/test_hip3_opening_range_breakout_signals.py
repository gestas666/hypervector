"""Tests for the frozen HIP-3 U.S. opening-range signal contract."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from hypervector.research.hip3_opening_range_breakout_signals import (
    Hip3OpeningRangeBreakoutConfig,
    build_hip3_opening_range_breakout_signals,
)


def _bars(session_date: date, *, wide_signal_bar: bool = False) -> pd.DataFrame:
    open_at = pd.Timestamp(session_date, tz="America/New_York") + pd.Timedelta(
        hours=9, minutes=30
    )
    open_at = open_at.tz_convert("UTC")
    index = pd.date_range(
        open_at - pd.Timedelta(minutes=70 * 15), periods=100, freq="15min"
    )
    close = np.linspace(90.0, 99.7, len(index))
    frame = pd.DataFrame(index=index)
    frame["open"] = close - 0.03
    frame["high"] = close + 0.05
    frame["low"] = close - 0.05
    frame["close"] = close
    frame["gap_before_bars"] = 0
    opening = [open_at, open_at + pd.Timedelta(minutes=15)]
    frame.loc[opening, ["open", "high", "low", "close"]] = [
        [99.8, 100.0, 99.7, 99.9],
        [99.9, 100.0, 99.8, 99.95],
    ]
    signal_at = open_at + pd.Timedelta(minutes=30)
    signal_low = 99.3 if wide_signal_bar else 100.15
    frame.loc[signal_at, ["open", "high", "low", "close"]] = [
        100.2,
        100.4,
        signal_low,
        100.3,
    ]
    return frame


def test_completed_opening_range_emits_one_long_with_structural_two_r_exit() -> None:
    bars = _bars(date(2026, 6, 16))
    config = Hip3OpeningRangeBreakoutConfig(clearance_bps=17.5)

    signals = build_hip3_opening_range_breakout_signals(bars, config)

    entry_at = pd.Timestamp("2026-06-16T14:00:00Z")
    exit_at = pd.Timestamp("2026-06-16T19:45:00Z")
    assert signals.index[signals["long_entry"]].tolist() == [entry_at]
    assert signals.at[entry_at, "stop_price"] == pytest.approx(100.14955)
    assert signals.at[entry_at, "target_price"] == pytest.approx(100.6009)
    assert signals.at[entry_at, "signal_name"].endswith("long@15m")
    assert bool(signals.at[exit_at, "long_exit"])
    assert signals["execution_authority"].eq("none").all()


def test_entry_is_skipped_when_structural_stop_exceeds_frozen_ceiling() -> None:
    bars = _bars(date(2026, 6, 16), wide_signal_bar=True)
    config = Hip3OpeningRangeBreakoutConfig(clearance_bps=17.5)

    signals = build_hip3_opening_range_breakout_signals(bars, config)

    assert not signals["long_entry"].any()
    assert signals["stop_distance_rejected"].sum() == 1


def test_official_2026_nyse_holiday_cannot_emit_an_entry() -> None:
    bars = _bars(date(2026, 6, 19))
    config = Hip3OpeningRangeBreakoutConfig(clearance_bps=17.5)

    signals = build_hip3_opening_range_breakout_signals(bars, config)

    assert not signals["long_entry"].any()
    assert not signals["short_entry"].any()
    holiday = signals.index.tz_convert("America/New_York").date == date(2026, 6, 19)
    assert not signals.loc[holiday, "session_eligible"].any()
