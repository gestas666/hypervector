"""Causal tests for the Trend Levels structural translation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_trend_levels import (
    TrendLevelsConfig,
    build_trend_levels,
)


def _bars(rows: int = 80) -> pd.DataFrame:
    """Return deterministic 30m structure with rising then falling extremes."""
    up = np.linspace(100.0, 118.0, rows // 2)
    down = np.linspace(118.0, 90.0, rows - rows // 2)
    close = np.concatenate((up, down))
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="30min", tz="UTC"
            ),
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.ones(rows),
        }
    )


def test_trend_levels_tracks_completed_episode_structure() -> None:
    """Trend state and episode levels must be backend-visible at bar close."""
    result = build_trend_levels(
        _bars(), bar_minutes=30, config=TrendLevelsConfig(lookback=10)
    )
    ready = result.loc[result["trend_state"].ne(0)]

    assert set(ready["trend_state"].unique()) == {-1, 1}
    assert ready["episode_bars"].ge(1).all()
    assert ready.loc[ready["episode_bars"].gt(1), "episode_mid"].notna().all()
    assert (
        result["decision_time_utc"] == result["bar_open_at"] + pd.Timedelta(minutes=30)
    ).all()


def test_ambiguous_hold_does_not_invent_direction_on_flat_extremes() -> None:
    """A simultaneous rolling high/low must remain neutral without prior state."""
    bars = _bars(20)
    bars[["open", "high", "low", "close"]] = 100.0

    corrected = build_trend_levels(
        bars,
        bar_minutes=30,
        config=TrendLevelsConfig(lookback=5, ambiguity_policy="hold"),
    )
    source = build_trend_levels(
        bars,
        bar_minutes=30,
        config=TrendLevelsConfig(lookback=5, ambiguity_policy="source_exact"),
    )

    assert corrected["trend_state"].eq(0).all()
    assert corrected["ambiguous_extreme"].iloc[4:].all()
    assert source["trend_state"].iloc[4:].eq(-1).all()


def test_trend_levels_is_append_invariant() -> None:
    """Future bars must not revise prior state, levels, duration, or delta."""
    bars = _bars()
    config = TrendLevelsConfig(lookback=10, ambiguity_policy="hold")
    before = build_trend_levels(bars.iloc[:55], bar_minutes=30, config=config)
    after = build_trend_levels(bars, bar_minutes=30, config=config).iloc[:55]

    pd.testing.assert_frame_equal(before, after.reset_index(drop=True))
