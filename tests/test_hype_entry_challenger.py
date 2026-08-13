"""Tests for the report-only HYPE entry return challengers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.ml.hype_entry_challenger import (
    HYPE_ENTRY_MODEL_CANDIDATES,
    evaluate_hype_entry_challengers,
)
from hypervector.research.hype_breakout_entry_features import (
    HYPE_ENTRY_ATTRIBUTION_FEATURES,
)


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
        rows.append(row)
    return pd.DataFrame(rows)


def test_challenger_uses_outcome_purged_embargoed_folds() -> None:
    """Training outcomes and feature windows must predate every test block."""
    rows = _rows()

    result = evaluate_hype_entry_challengers(
        rows,
        n_splits=3,
        embargo_minutes=60,
    )

    assert len(result.folds) == 3
    prepared = result.rows
    for fold in result.folds:
        train_outcome = prepared.iloc[fold.train_indices]["outcome_ts_ms"].max()
        test_signal = prepared.iloc[fold.test_indices]["signal_ts_ms"].min()
        assert train_outcome < test_signal - 60 * 60_000


def test_challenger_keeps_exact_search_and_after_cost_evidence() -> None:
    """Only the frozen two candidates may emit gross forecasts and net tails."""
    result = evaluate_hype_entry_challengers(_rows(), n_splits=3)

    assert set(result.predictions["candidate"]) == set(HYPE_ENTRY_MODEL_CANDIDATES)
    assert set(result.fold_metrics["candidate"]) == set(HYPE_ENTRY_MODEL_CANDIDATES)
    assert np.isfinite(result.predictions["predicted_gross_return_bps"]).all()
    assert "actual_net_return_bps" in result.predictions
    assert result.report["trial_accounting"]["model_candidates"] == 2
    assert result.report["contract"]["execution_authority"] == "none"
    assert result.report["contract"]["runtime_strategy_changed"] is False
    for summary in result.report["candidates"].values():
        assert summary["gross_spread_hurdle_bps"] == 26.0
        assert summary["valid_rank_ic_folds"] == 3


def test_challenger_is_deterministic() -> None:
    """Fixed folds and model seeds must reproduce identical OOS evidence."""
    rows = _rows()

    first = evaluate_hype_entry_challengers(rows, n_splits=2)
    second = evaluate_hype_entry_challengers(rows, n_splits=2)

    pd.testing.assert_frame_equal(first.predictions, second.predictions)
    pd.testing.assert_frame_equal(first.fold_metrics, second.fold_metrics)
    assert first.report == second.report


def test_challenger_rejects_shuffled_or_nonfinite_evidence() -> None:
    """Temporal disorder and missing causal features must fail explicitly."""
    shuffled = _rows().sample(frac=1.0, random_state=7).reset_index(drop=True)
    with pytest.raises(ValueError, match="ordered"):
        evaluate_hype_entry_challengers(shuffled)

    missing = _rows()
    missing.loc[0, HYPE_ENTRY_ATTRIBUTION_FEATURES[0]] = np.nan
    with pytest.raises(ValueError, match="finite"):
        evaluate_hype_entry_challengers(missing)
