"""Integrated causal feature and entry tests for the four-Pine stack."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_features import (
    PineStackFeatureConfig,
    build_pine_stack_features,
)
from hypervector.research.pine_stack_signals import (
    compose_pine_stack_entries,
    declared_pine_stack_candidates,
)
from hypervector.research.pine_stack_trend_levels import TrendLevelsConfig


def _bars(rows: int = 1_100, minutes: int = 15) -> pd.DataFrame:
    """Return deterministic directional waves for integrated signal coverage."""
    positions = np.arange(rows, dtype=float)
    close = 100.0 + 0.008 * positions + 9.0 * np.sin(positions / 13.0)
    open_ = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2025-01-01", periods=rows, freq=f"{minutes}min", tz="UTC"
            ),
            "open": open_,
            "high": np.maximum(open_, close) + 0.9,
            "low": np.minimum(open_, close) - 0.9,
            "close": close,
            "volume": 700.0 + 200.0 * np.sin(positions / 6.0),
        }
    )


def test_integrated_features_keep_backend_source_times_and_support() -> None:
    """Every visual/trading layer must share one completed native-bar identity."""
    features = build_pine_stack_features(_bars(), bar_minutes=15)

    assert len(features) == 1_100
    assert features["decision_time_utc"].is_monotonic_increasing
    assert {
        "cs_selected_factor",
        "cs_trend_state",
        "trend_levels_state",
        "sentiment_score",
        "tp_density_match_score",
        "tp_directional_pool_size",
    }.issubset(features.columns)
    assert features["execution_authority"].eq("none").all()


def test_integrated_features_and_entries_are_append_invariant() -> None:
    """Appending future bars must preserve historical state and entry rows."""
    bars = _bars()
    config = PineStackFeatureConfig(trend_levels=TrendLevelsConfig(lookback=20))
    before = build_pine_stack_features(bars.iloc[:900], bar_minutes=15, config=config)
    after = build_pine_stack_features(bars, bar_minutes=15, config=config).iloc[:900]
    pd.testing.assert_frame_equal(before, after.reset_index(drop=True))

    before_entries = compose_pine_stack_entries(before, symbol="BTC")
    after_entries = compose_pine_stack_entries(after, symbol="BTC")
    pd.testing.assert_frame_equal(before_entries, after_entries)


def test_entry_ablation_preserves_base_events_and_filtered_subsets() -> None:
    """Confluence variants must not erase the observable CS base event stream."""
    features = build_pine_stack_features(_bars(), bar_minutes=15)
    entries = compose_pine_stack_entries(features, symbol="BTC")
    base = entries.loc[entries["candidate"].eq("cs_base")]

    assert not base.empty
    assert set(base["side"]) == {"long", "short"}
    declared = {
        "cs_base",
        "cs_trend",
        "cs_sentiment_55",
        "cs_trend_sentiment_55",
        "cs_sentiment_60",
        "cs_trend_sentiment_60",
    }
    assert set(declared_pine_stack_candidates()) == declared
    assert set(entries["candidate"]).issubset(declared)
    base_keys = set(zip(base["decision_time_utc"], base["side"], strict=True))
    for candidate in set(entries["candidate"]) - {"cs_base"}:
        selected = entries.loc[entries["candidate"].eq(candidate)]
        keys = set(zip(selected["decision_time_utc"], selected["side"], strict=True))
        assert keys.issubset(base_keys)
    assert entries["execution_authority"].eq("none").all()
