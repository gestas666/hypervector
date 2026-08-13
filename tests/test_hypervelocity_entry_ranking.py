"""Tests for annotation-only creator entry-time ranking research."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.hypervelocity_entry_ranking import (
    build_entry_ranking_dataset,
    evaluate_entry_ranking,
)
from hypervector.research.hypervelocity_metalabel import BASE_FEATURE_NAMES


def _candidate_rows() -> pd.DataFrame:
    index = pd.date_range("2026-01-01T00:01:00Z", periods=4, freq="1min")
    values: dict[str, object] = {
        "direction": ["long", "long", "short", "short"],
    }
    values.update(
        {
            name: np.arange(4, dtype=float) + offset
            for offset, name in enumerate(BASE_FEATURE_NAMES)
        }
    )
    return pd.DataFrame(values, index=index)


def _source_entries() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_id": ["matched", "opposed"],
            "event_time": [
                "2026-01-01T00:01:30Z",
                "2026-01-01T00:03:30Z",
            ],
            "side": ["long", "long"],
        }
    )


def test_dataset_maps_only_exact_side_to_latest_available_minute() -> None:
    candidates = _candidate_rows()
    source = _source_entries()

    dataset = build_entry_ranking_dataset(candidates, source)

    assert dataset.candidates["is_observed_entry"].tolist() == [
        True,
        False,
        False,
        False,
    ]
    assert dataset.candidates["label_kind"].tolist() == [
        "observed_entry",
        "unlabeled",
        "unlabeled",
        "unlabeled",
    ]
    assert dataset.candidates["source_id"].iloc[0] == "matched"
    assert dataset.source_alignment["matched_direction"].tolist() == [True, False]
    assert dataset.source_alignment["mapped_candidate_time_utc"].tolist() == [
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:03:00+00:00",
    ]
    assert dataset.source_alignment["reason"].tolist() == [
        "matched",
        "direction_mismatch",
    ]


def test_dataset_retains_ineligible_source_inside_explicit_evidence_bounds() -> None:
    source = pd.DataFrame(
        {
            "source_id": ["pre-candidate"],
            "event_time": ["2026-01-01T00:00:30Z"],
            "side": ["long"],
        }
    )

    dataset = build_entry_ranking_dataset(
        _candidate_rows(),
        source,
        evidence_start=pd.Timestamp("2026-01-01T00:00:00Z"),
        evidence_end=pd.Timestamp("2026-01-01T00:05:00Z"),
    )

    assert dataset.candidates["is_observed_entry"].sum() == 0
    assert dataset.source_alignment["mapped_candidate_time_utc"].iloc[0] == (
        "2026-01-01T00:00:00+00:00"
    )
    assert dataset.source_alignment["reason"].iloc[0] == "no_candidate_at_minute"


def test_dataset_does_not_mutate_inputs() -> None:
    candidates = _candidate_rows()
    source = _source_entries()
    expected_candidates = candidates.copy(deep=True)
    expected_source = source.copy(deep=True)

    build_entry_ranking_dataset(candidates, source)

    pd.testing.assert_frame_equal(candidates, expected_candidates)
    pd.testing.assert_frame_equal(source, expected_source)


def test_dataset_rejects_duplicate_source_mapping() -> None:
    candidates = _candidate_rows()
    source = pd.DataFrame(
        {
            "source_id": ["one", "two"],
            "event_time": [
                "2026-01-01T00:01:10Z",
                "2026-01-01T00:01:20Z",
            ],
            "side": ["long", "long"],
        }
    )

    with pytest.raises(ValueError, match="same candidate minute"):
        build_entry_ranking_dataset(candidates, source)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("side", "flat", "source side"),
        ("event_time", "2025-12-31T23:59:00Z", "outside candidate bounds"),
    ],
)
def test_dataset_rejects_invalid_source_rows(
    column: str,
    value: str,
    message: str,
) -> None:
    source = _source_entries()
    source.loc[0, column] = value

    with pytest.raises(ValueError, match=message):
        build_entry_ranking_dataset(_candidate_rows(), source)


def test_dataset_rejects_missing_declared_feature() -> None:
    candidates = _candidate_rows().drop(columns=[BASE_FEATURE_NAMES[-1]])

    with pytest.raises(ValueError, match="candidate features missing"):
        build_entry_ranking_dataset(candidates, _source_entries())


def _ranking_candidates(*, include_extreme_test_row: bool = False) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for day_number, day in enumerate(("2026-01-01", "2026-01-02", "2026-01-03")):
        index = pd.date_range(f"{day}T00:00:00Z", periods=20, freq="1min")
        base = np.arange(20, dtype=float) + day_number
        values: dict[str, object] = {"direction": ["long"] * len(index)}
        values.update(
            {
                name: base + feature_number
                for feature_number, name in enumerate(BASE_FEATURE_NAMES)
            }
        )
        frames.append(pd.DataFrame(values, index=index))
    result = pd.concat(frames)
    if include_extreme_test_row:
        row = result.iloc[[-1]].copy()
        row.index = pd.DatetimeIndex(["2026-01-03T00:20:00Z"])
        row.loc[:, BASE_FEATURE_NAMES] = 1_000_000.0
        result = pd.concat([result, row])
    return result


def _ranking_source() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_id": ["day-one", "day-three"],
            "event_time": [
                "2026-01-01T00:02:30Z",
                "2026-01-03T00:03:30Z",
            ],
            "side": ["long", "long"],
        }
    )


def test_ranking_folds_train_only_on_strictly_prior_days() -> None:
    dataset = build_entry_ranking_dataset(_ranking_candidates(), _ranking_source())

    result = evaluate_entry_ranking(dataset)

    assert result.fold_audit["test_day_utc"].tolist() == [
        "2026-01-02",
        "2026-01-03",
    ]
    assert (
        pd.to_datetime(result.fold_audit["train_max_time_utc"], utc=True)
        < pd.to_datetime(result.fold_audit["test_day_utc"], utc=True)
    ).all()
    day_two = result.fold_metrics.loc[
        result.fold_metrics["test_day_utc"].eq("2026-01-02")
    ]
    assert day_two["test_positives"].eq(0).all()
    assert day_two["positive_percentile_mean"].isna().all()


def test_fold_local_preprocessing_ignores_other_heldout_values() -> None:
    base = build_entry_ranking_dataset(_ranking_candidates(), _ranking_source())
    extended = build_entry_ranking_dataset(
        _ranking_candidates(include_extreme_test_row=True), _ranking_source()
    )

    base_result = evaluate_entry_ranking(base)
    extended_result = evaluate_entry_ranking(extended)
    common_time = "2026-01-03T00:05:00+00:00"
    for model in ("logistic", "lightgbm"):
        base_score = base_result.predictions.loc[
            base_result.predictions["candidate_time_utc"].eq(common_time)
            & base_result.predictions["model"].eq(model),
            "score",
        ].item()
        extended_score = extended_result.predictions.loc[
            extended_result.predictions["candidate_time_utc"].eq(common_time)
            & extended_result.predictions["model"].eq(model),
            "score",
        ].item()
        assert extended_score == pytest.approx(base_score, abs=1e-12)


def test_ranking_result_is_deterministic_and_declares_searched_set() -> None:
    dataset = build_entry_ranking_dataset(_ranking_candidates(), _ranking_source())

    first = evaluate_entry_ranking(dataset)
    second = evaluate_entry_ranking(dataset)

    assert first.searched_set == (
        "uniform",
        "strength_only",
        "logistic",
        "lightgbm",
    )
    pd.testing.assert_frame_equal(first.fold_metrics, second.fold_metrics)
    pd.testing.assert_frame_equal(first.predictions, second.predictions)
    assert set(first.summary) == set(first.searched_set)
