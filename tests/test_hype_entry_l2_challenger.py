"""Tests for predeclared HYPE bar/L2 entry-model challengers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.ml.hype_entry_l2_challenger import (
    HYPE_ENTRY_L2_MODEL_CANDIDATES,
    evaluate_hype_entry_l2_challengers,
)
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
)
from hypervector.research.hype_entry_l2_features import HYPE_ENTRY_L2_FEATURES


def test_l2_challenger_runs_exact_six_candidate_comparison() -> None:
    """Bar, L2, and combined controls use Ridge and LightGBM exactly once."""
    result = evaluate_hype_entry_l2_challengers(_rows(), n_splits=3)

    assert set(result.predictions["candidate"]) == set(HYPE_ENTRY_L2_MODEL_CANDIDATES)
    assert set(result.fold_metrics["candidate"]) == set(HYPE_ENTRY_L2_MODEL_CANDIDATES)
    assert len(result.fold_metrics) == 18
    assert result.report["trial_accounting"]["model_candidates"] == 6
    assert result.report["trial_accounting"]["hyperparameter_sweeps"] == 0
    assert result.report["acceptance"]["gross_spread_hurdle_bps"] == 26.0
    assert result.report["contract"]["execution_authority"] == "none"


def test_l2_challenger_keeps_post_entry_diagnostics_out_of_features() -> None:
    """Execution observations may be reported but never enter model matrices."""
    rows = _rows()
    rows["l2_post_mid_move_bps"] = np.linspace(-100.0, 100.0, len(rows))

    result = evaluate_hype_entry_l2_challengers(rows, n_splits=2)

    sets = result.report["dataset"]["feature_sets"]
    assert "l2_post_mid_move_bps" not in sets["l2_only"]
    assert "l2_post_mid_move_bps" not in sets["bar_plus_l2"]


def test_l2_challenger_is_deterministic() -> None:
    """Fixed folds and seeds reproduce identical six-way OOS evidence."""
    rows = _rows()

    first = evaluate_hype_entry_l2_challengers(rows, n_splits=2)
    second = evaluate_hype_entry_l2_challengers(rows, n_splits=2)

    pd.testing.assert_frame_equal(first.predictions, second.predictions)
    pd.testing.assert_frame_equal(first.fold_metrics, second.fold_metrics)
    assert first.report == second.report


def _rows(samples: int = 240) -> pd.DataFrame:
    times = pd.date_range("2025-01-01", periods=samples, freq="3h", tz="UTC")
    latent = np.sin(np.arange(samples, dtype=float) / 8.0)
    rows: list[dict[str, object]] = []
    for index, stamp in enumerate(times):
        row: dict[str, object] = {
            "entry_side": "long" if index % 2 == 0 else "short",
            "signal_time_utc": stamp.isoformat(),
            "entry_time_utc": (stamp + pd.Timedelta(minutes=1)).isoformat(),
            "exit_time_utc": (stamp + pd.Timedelta(minutes=90)).isoformat(),
            "gross_return_bps": 80.0 * latent[index] - 4.0,
            "net_return_bps": 80.0 * latent[index] - 17.0,
            "exit_reason": "maximum_hold",
        }
        for feature_index, name in enumerate(HYPE_ENTRY_ATTRIBUTION_FEATURES):
            row[name] = latent[index] + feature_index / 100.0
        for feature_index, name in enumerate(HYPE_ENTRY_L2_FEATURES):
            row[name] = latent[index] * 0.7 + feature_index / 200.0
        rows.append(row)
    return pd.DataFrame(rows)
