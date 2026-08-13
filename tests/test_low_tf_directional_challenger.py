"""Tests for purged low-timeframe directional model challengers."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from hypervector.ml.low_tf_directional_challenger import (
    CANDIDATE_NAMES,
    RETURN_CANDIDATE_NAMES,
    evaluate_low_tf_directional_challengers,
    evaluate_low_tf_return_challengers,
    return_lightgbm_params,
)
from hypervector.research.low_tf_l2_dataset import FEATURE_NAMES


def _rows(signals: int = 180) -> pd.DataFrame:
    starts = pd.date_range("2026-01-01", periods=signals, freq="5min", tz="UTC")
    rows: list[dict[str, object]] = []
    for index, stamp in enumerate(starts):
        momentum = float(np.sin(index / 5.0))
        for side, sign in (("long", 1.0), ("short", -1.0)):
            row: dict[str, object] = {
                "signal_ts_ms": int(stamp.timestamp() * 1_000),
                "outcome_ts_ms": int(
                    (stamp + pd.Timedelta(minutes=60)).timestamp() * 1_000
                ),
                "side": side,
                "target_hit": int(momentum * sign > 0.0),
                "gross_return_bps": 20.0 * momentum * sign - 4.0,
            }
            for feature_index, name in enumerate(FEATURE_NAMES, start=1):
                row[name] = momentum + feature_index / 100.0
            rows.append(row)
    return pd.DataFrame(rows)


def test_challenger_keeps_both_sides_of_signal_in_same_fold() -> None:
    """Long and short labels from one instant must never leak across folds."""
    result = evaluate_low_tf_directional_challengers(_rows(), n_splits=3)

    assert set(result.predictions["candidate"]) == set(CANDIDATE_NAMES)
    for (_, _, signal), group in result.predictions.groupby(
        ["candidate", "fold_id", "signal_ts_ms"]
    ):
        assert set(group["side"]) == {"long", "short"}, signal


def test_challenger_folds_are_outcome_purged_and_embargoed() -> None:
    """Every training outcome must precede the test signal embargo boundary."""
    rows = _rows()
    result = evaluate_low_tf_directional_challengers(
        rows,
        n_splits=3,
        embargo_minutes=60,
    )

    for fold in result.folds:
        train_outcome = rows.iloc[fold.train_indices]["outcome_ts_ms"].max()
        test_signal = rows.iloc[fold.test_indices]["signal_ts_ms"].min()
        assert train_outcome < test_signal - 60 * 60_000
        labels = rows.iloc[fold.test_indices]["target_hit"]
        assert set(labels) == {0, 1}


def test_challenger_predictions_are_deterministic() -> None:
    """Fixed folds and model seeds must reproduce identical probabilities."""
    rows = _rows()

    first = evaluate_low_tf_directional_challengers(rows, n_splits=2)
    second = evaluate_low_tf_directional_challengers(rows, n_splits=2)

    pd.testing.assert_frame_equal(first.predictions, second.predictions)
    pd.testing.assert_frame_equal(first.fold_metrics, second.fold_metrics)


def test_challenger_rejects_shuffled_rows() -> None:
    """The evaluator must not silently sort a temporally invalid dataset."""
    shuffled = _rows().sample(frac=1.0, random_state=17).reset_index(drop=True)

    with pytest.raises(ValueError, match="ordered"):
        evaluate_low_tf_directional_challengers(shuffled)


def test_challenger_rejects_missing_side_pair() -> None:
    """Each market timestamp requires exactly one long and one short label."""
    rows = _rows().drop(index=1).reset_index(drop=True)

    with pytest.raises(ValueError, match="long and short"):
        evaluate_low_tf_directional_challengers(rows)


def test_return_challenger_predicts_bps_with_purged_side_pairs() -> None:
    """Return models must emit causal paired-side out-of-sample forecasts."""
    rows = _rows()

    result = evaluate_low_tf_return_challengers(rows, n_splits=3)

    assert set(result.predictions["candidate"]) == set(RETURN_CANDIDATE_NAMES)
    assert np.isfinite(result.predictions["predicted_gross_return_bps"]).all()
    for (_, _, signal), group in result.predictions.groupby(
        ["candidate", "fold_id", "signal_ts_ms"]
    ):
        assert set(group["side"]) == {"long", "short"}, signal
    for fold in result.folds:
        train_outcome = rows.iloc[fold.train_indices]["outcome_ts_ms"].max()
        test_signal = rows.iloc[fold.test_indices]["signal_ts_ms"].min()
        assert train_outcome < test_signal - 60 * 60_000


def test_return_challenger_is_deterministic() -> None:
    """Fixed regression contracts must reproduce identical OOS forecasts."""
    rows = _rows()

    first = evaluate_low_tf_return_challengers(rows, n_splits=2)
    second = evaluate_low_tf_return_challengers(rows, n_splits=2)

    pd.testing.assert_frame_equal(first.predictions, second.predictions)
    pd.testing.assert_frame_equal(first.fold_metrics, second.fold_metrics)


def test_return_challenger_rejects_nonfinite_outcomes() -> None:
    """Missing realized returns must fail rather than become training labels."""
    rows = _rows()
    rows.loc[0, "gross_return_bps"] = np.nan

    with pytest.raises(ValueError, match="gross returns"):
        evaluate_low_tf_return_challengers(rows)


def test_return_challenger_handles_constant_fold_predictions_without_warning() -> None:
    """Undefined rank correlation must not leak numerical runtime warnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = evaluate_low_tf_return_challengers(_rows(), n_splits=2)

    assert len(result.fold_metrics) == 4


def test_return_lightgbm_optimizes_conditional_mean() -> None:
    """Expected-gross forecasts require a mean rather than median objective."""
    params = return_lightgbm_params()

    assert params["objective"] == "regression"
    assert params["metric"] == "l2"
