"""Causality contracts for rebuilt Hulk market-quality evidence."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.hulk_smash_quality import build_hulk_quality_frame


def _bars(rows: int = 180) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC")
    phase = np.arange(rows, dtype=float)
    close = 100.0 + 0.03 * phase + np.sin(phase / 7.0)
    opening = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {
            "open": opening,
            "high": np.maximum(opening, close) + 0.3,
            "low": np.minimum(opening, close) - 0.3,
            "close": close,
            "volume": 10.0 + np.cos(phase / 5.0),
        },
        index=index,
    )


def test_quality_frame_is_append_invariant_and_categorical_states_are_bounded() -> None:
    """Future bars cannot revise ADX, squeeze, trend, or HA quality state."""
    bars = _bars()

    prefix = build_hulk_quality_frame(bars.iloc[:150])
    full = build_hulk_quality_frame(bars).loc[prefix.index]

    pd.testing.assert_frame_equal(prefix, full)
    assert set(full["supertrend_direction"].unique()).issubset({-1, 1})
    assert set(full["di_direction"].unique()).issubset({-1, 0, 1})
    assert full["squeeze_release"].dtype == bool
    assert full["ha_choppy"].dtype == bool


def test_quality_warmup_stays_unknown_instead_of_receiving_points() -> None:
    """ADX unavailability must remain NaN during its two-stage warmup."""
    result = build_hulk_quality_frame(_bars(80))

    assert result["adx"].iloc[:26].isna().all()
    assert not result["squeeze_release"].iloc[:20].any()
