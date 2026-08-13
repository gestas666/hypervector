"""Causal tests for the SuperTrend TP Dimensions translation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_tp_dimensions import (
    TpDimensionsConfig,
    build_tp_dimensions,
)


def _bars(rows: int = 1_000) -> pd.DataFrame:
    """Return deterministic 15m waves with many confirmed directional pivots."""
    positions = np.arange(rows, dtype=float)
    close = 100.0 + 0.004 * positions + 8.0 * np.sin(positions / 8.0)
    open_ = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="15min", tz="UTC"
            ),
            "open": open_,
            "high": np.maximum(open_, close) + 0.7,
            "low": np.minimum(open_, close) - 0.7,
            "close": close,
            "volume": 500.0 + 150.0 * np.sin(positions / 5.0),
        }
    )


def test_tp_dimensions_exposes_density_and_support_not_probability() -> None:
    """A usable score must include directional and conditional sample support."""
    config = TpDimensionsConfig(
        pivot_width=2,
        minimum_directional_pool=5,
        minimum_conditional_support=1,
    )
    result = build_tp_dimensions(_bars(), bar_minutes=15, config=config)
    scored = result.dropna(subset=["density_match_score"])

    assert not scored.empty
    assert scored["density_match_score"].between(0.0, 100.0).all()
    assert scored["directional_pool_size"].ge(5).all()
    assert scored["minimum_axis_support"].ge(1).all()
    assert result["score_semantics"].eq("density_match_not_probability").all()
    assert set(result["supertrend_direction"].unique()).issubset({-1, 0, 1})


def test_tp_dimensions_withholds_sparse_raw_score() -> None:
    """A sparse 100 score must remain visible but ineligible for an exit."""
    config = TpDimensionsConfig(
        pivot_width=2,
        minimum_directional_pool=10_000,
        minimum_conditional_support=1,
    )
    result = build_tp_dimensions(_bars(400), bar_minutes=15, config=config)

    assert result["density_match_raw"].notna().any()
    assert result["density_match_score"].isna().all()
    assert result["insufficient_support"].any()


def test_tp_dimensions_is_append_invariant() -> None:
    """Future bars must not revise pools, scores, support, or confirmed pivots."""
    bars = _bars()
    config = TpDimensionsConfig(
        pivot_width=2,
        minimum_directional_pool=5,
        minimum_conditional_support=1,
    )
    before = build_tp_dimensions(bars.iloc[:750], bar_minutes=15, config=config)
    after = build_tp_dimensions(bars, bar_minutes=15, config=config).iloc[:750]

    pd.testing.assert_frame_equal(before, after.reset_index(drop=True))
