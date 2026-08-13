"""Forward-only contracts for the zero-capital four-Pine observer."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_forward_observer import (
    PineStackForwardObserver,
    prepare_completed_pine_features,
)


def _raw_minutes(rows: int = 615) -> pd.DataFrame:
    """Return exact deterministic one-minute source candles."""
    positions = np.arange(rows, dtype=float)
    close = 100.0 + np.sin(positions / 20.0)
    open_ = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-08-01T00:00:00Z", periods=rows, freq="1min"
            ),
            "open": open_,
            "high": np.maximum(open_, close) + 0.1,
            "low": np.minimum(open_, close) - 0.1,
            "close": close,
            "volume": 10.0 + positions,
            "source": "hl",
        }
    )


def _features() -> pd.DataFrame:
    """Return two complete backend feature rows around activation."""
    components = {
        f"sentiment_{name}": [45.0, 60.0]
        for name in (
            "rsi",
            "stochastic",
            "stochastic_rsi",
            "cci",
            "bull_bear_power",
            "moving_average",
            "vwap",
            "bollinger",
            "supertrend",
            "linear_regression",
            "market_structure",
        )
    }
    return pd.DataFrame(
        {
            "bar_open_at": pd.to_datetime(
                ["2026-08-01T00:00:00Z", "2026-08-01T00:30:00Z"]
            ),
            "decision_time_utc": pd.to_datetime(
                ["2026-08-01T00:30:00Z", "2026-08-01T01:00:00Z"]
            ),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000.0, 1100.0],
            "cs_selected_factor": [4.5, 5.0],
            "cs_trailing_stop": [99.5, 100.5],
            "cs_trend_state": [-1, 1],
            "cs_long_onset": [False, True],
            "cs_short_onset": [False, False],
            "trend_levels_state": [-1, 1],
            "trend_levels_episode_bars": [4, 1],
            "trend_levels_episode_high": [102.0, 103.0],
            "trend_levels_episode_low": [98.0, 100.0],
            "trend_levels_episode_mid": [100.0, np.nan],
            "trend_levels_close_location_delta_pct": [-50.0, np.nan],
            "trend_levels_ambiguous_extreme": [False, False],
            "sentiment_score": [45.0, 60.0],
            "component_support": [11, 11],
            **components,
            "tp_density_match_raw": [70.0, 82.0],
            "tp_density_match_score": [np.nan, 82.0],
            "tp_directional_pool_size": [20, 55],
            "tp_minimum_axis_support": [3, 8],
            "tp_insufficient_support": [True, False],
            "tp_relative_volume_score": [60.0, 80.0],
            "tp_time_of_day_score": [70.0, 90.0],
            "tp_range_position_score": [80.0, 76.0],
            "execution_authority": "none",
        }
    )


def test_prepare_features_excludes_forming_native_bar() -> None:
    """Only fully completed 30m bars may reach the observer ledger."""
    features = prepare_completed_pine_features(
        _raw_minutes(), observed_at=pd.Timestamp("2026-08-01T10:14:30Z")
    )

    assert features["bar_open_at"].iloc[-1] == pd.Timestamp("2026-08-01T09:30:00Z")
    assert features["decision_time_utc"].max() <= pd.Timestamp("2026-08-01T10:14:30Z")
    assert features["execution_authority"].eq("none").all()


def test_observer_writes_history_and_fresh_decision_without_order_authority(
    tmp_path: Path,
) -> None:
    """Startup history is inert while a fresh post-activation onset is visible."""
    ledger = tmp_path / "decisions.jsonl"
    observer = PineStackForwardObserver(
        activated_at=pd.Timestamp("2026-08-01T00:45:00Z"), ledger_path=ledger
    )

    rows = observer.observe(
        _features(), observed_at=pd.Timestamp("2026-08-01T01:00:15Z")
    )

    assert [row["action"] for row in rows] == [
        "session_start",
        "regime_history",
        "regime_observation",
    ]
    latest = rows[-1]
    assert latest["entry_allowed"] is True
    assert latest["entry_direction"] == "long"
    assert latest["execution_authority"] == "none"
    assert latest["submitted"] is False
    assert latest["place_attempted"] is False
    assert latest["pine_sentiment_components"]["rsi"] == 60.0
    assert latest["pine_tp_score_semantics"] == "density_match_not_probability"

    restarted = PineStackForwardObserver(
        activated_at=pd.Timestamp("2026-08-01T01:01:00Z"), ledger_path=ledger
    )
    assert (
        restarted.observe(_features(), observed_at=pd.Timestamp("2026-08-01T01:02:00Z"))
        == ()
    )
    persisted = [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
    ]
    assert len(persisted) == 3


def test_stale_post_activation_onset_is_recorded_but_not_actionable(
    tmp_path: Path,
) -> None:
    """Downtime cannot retro-trigger an otherwise valid Pine onset."""
    observer = PineStackForwardObserver(
        activated_at=pd.Timestamp("2026-08-01T00:45:00Z"),
        ledger_path=tmp_path / "stale.jsonl",
    )

    rows = observer.observe(
        _features(), observed_at=pd.Timestamp("2026-08-01T01:10:00Z")
    )

    latest = rows[-1]
    assert latest["pine_candidate_entry"] is True
    assert latest["fresh_at_observation"] is False
    assert latest["entry_allowed"] is False
    assert latest["decision_action"] == "stale_long_onset_observe_only"
