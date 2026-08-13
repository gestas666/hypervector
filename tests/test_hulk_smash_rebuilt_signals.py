"""Contracts for the rebuilt data-driven Hulk Smash core."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.hulk_smash_rebuilt_signals import (
    RebuiltHulkConfig,
    evaluate_rebuilt_hulk_signals,
)


def _inputs(rows: int = 80) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC")
    close = np.linspace(100.0, 104.0, rows)
    bars = pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 10.0,
        },
        index=index,
    )
    components = pd.DataFrame(
        {
            "wt1": 0.0,
            "wave_cross": 0,
            "money_flow_direction": 1,
            "volume_ratio": 1.2,
            "ema_trend": 1,
            "krown_direction": 1,
            "krown_zone_context": 0,
        },
        index=index,
    )
    quality = pd.DataFrame(
        {
            "supertrend_direction": 1,
            "adx": 30.0,
            "di_direction": 1,
            "squeeze_on": False,
            "squeeze_release": False,
            "ha_choppy": False,
        },
        index=index,
    )
    return bars, components, quality


def test_continuation_is_named_scored_and_triggered_once() -> None:
    """A WaveTrend event produces one transparent Hulk continuation decision."""
    bars, components, quality = _inputs()
    components.iloc[-1, components.columns.get_loc("wave_cross")] = 1

    result = evaluate_rebuilt_hulk_signals(
        bars, components, quality, RebuiltHulkConfig(minimum_score=8)
    )

    assert len(result) == 1
    row = result.iloc[0]
    assert row["candidate"] == "hulk_rebuilt_continuation_v1"
    assert row["side"] == "long"
    assert row["eligible"]
    assert row["score"] >= 8
    assert "wave_cross" in row["evidence"]


def test_krown_turn_can_time_a_trend_setup_without_repeated_entries() -> None:
    """Krown slope transition is an event trigger, not a persistent entry."""
    bars, components, quality = _inputs()
    components["krown_direction"] = 1
    components.iloc[-2, components.columns.get_loc("krown_direction")] = -1

    result = evaluate_rebuilt_hulk_signals(bars, components, quality)

    assert len(result) == 1
    assert result.iloc[0]["trigger"] == "krown_turn"


def test_short_continuation_is_symmetric() -> None:
    """The rebuilt core must not retain the legacy long-side bias."""
    bars, components, quality = _inputs()
    for column in ("money_flow_direction", "ema_trend", "krown_direction"):
        components[column] = -1
    quality["supertrend_direction"] = -1
    quality["di_direction"] = -1
    components.iloc[-1, components.columns.get_loc("wave_cross")] = -1

    result = evaluate_rebuilt_hulk_signals(bars, components, quality)

    assert len(result) == 1
    assert result.iloc[0]["side"] == "short"
    assert result.iloc[0]["stop_anchor"] == bars["high"].iloc[-5:].max()


def test_threshold_changes_disposition_without_deleting_decision() -> None:
    """AutoTune sees losing/rejected rows rather than hiding them."""
    bars, components, quality = _inputs()
    components.iloc[-1, components.columns.get_loc("wave_cross")] = 1

    result = evaluate_rebuilt_hulk_signals(
        bars, components, quality, RebuiltHulkConfig(minimum_score=99)
    )

    assert len(result) == 1
    assert not result.iloc[0]["eligible"]
    assert result.iloc[0]["reason"] == "score_below_99"


def test_signal_history_is_append_invariant() -> None:
    """Appending bars cannot add or remove earlier rebuilt Hulk decisions."""
    bars, components, quality = _inputs(90)
    components.iloc[60, components.columns.get_loc("wave_cross")] = 1

    prefix = evaluate_rebuilt_hulk_signals(
        bars.iloc[:70], components.iloc[:70], quality.iloc[:70]
    )
    full = evaluate_rebuilt_hulk_signals(bars, components, quality)
    comparable = full.loc[full["signal_time_utc"].isin(prefix["signal_time_utc"])]

    pd.testing.assert_frame_equal(
        prefix.reset_index(drop=True), comparable.reset_index(drop=True)
    )
