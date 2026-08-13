"""Frozen source-state challenger holdout scoring tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.ml.hypervelocity_source_challenger import (
    train_source_state_challengers,
)
from hypervector.ml.hypervelocity_source_challenger_holdout import (
    score_frozen_source_challengers,
    source_candidate_acceptance,
)
from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
)
from hypervector.research.hypervelocity_source_features import SOURCE_FEATURE_NAMES


def _rows(n_rows: int, *, offset: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(91 + offset)
    signal = (np.arange(n_rows, dtype=np.int64) + offset) * 3_600_000
    labels = (np.arange(n_rows) % 7 == 0).astype(int)
    frame = pd.DataFrame(
        {
            "lifecycle_id": np.arange(n_rows),
            "segment_id": "holdout" if offset else "training",
            "signal_ts_ms": signal,
            "outcome_ts_ms": signal + 600_000,
            "liquidation_risk": labels,
        }
    )
    features = (
        BASE_FEATURE_NAMES
        + BOOK_FEATURE_NAMES
        + SEQUENCE_BOOK_FEATURE_NAMES
        + SOURCE_FEATURE_NAMES
    )
    for name in features:
        frame[name] = rng.normal(size=n_rows) + labels * 0.1
    return frame


def _frozen_evidence(tmp_path: Path) -> tuple[Path, Path, Path]:
    training = _rows(240)
    model_dir = tmp_path / "models"
    result = train_source_state_challengers(training, model_dir)
    dataset = tmp_path / "dataset.parquet"
    training.to_parquet(dataset, index=False)
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "ok": True,
                "report_only": True,
                "runtime_strategy_changed": False,
                "forward_holdout_start_utc": "2026-01-09T00:00:00+00:00",
                "model_evidence": {
                    **{
                        name: file_evidence(path)
                        for name, path in result.model_paths.items()
                    },
                    "metadata": file_evidence(result.metadata_path),
                },
                "data_evidence": {"dataset": file_evidence(dataset)},
            }
        ),
        encoding="utf-8",
    )
    return report, dataset, model_dir


def test_scores_exact_frozen_source_models_without_modification(
    tmp_path: Path,
) -> None:
    """Source-state scoring must not retrain or alter persisted evidence."""
    report, dataset, model_dir = _frozen_evidence(tmp_path)
    before = {path.name: file_evidence(path) for path in model_dir.iterdir()}

    result = score_frozen_source_challengers(
        _rows(70, offset=1_000),
        training_report_path=report,
        training_dataset_path=dataset,
        model_dir=model_dir,
    )

    after = {path.name: file_evidence(path) for path in model_dir.iterdir()}
    assert before == after
    assert len(result.metrics) == 5
    assert result.metrics["base_rate"]["samples"] == 70
    assert result.predictions["candidate"].nunique() == 5
    expected_rate = float(pd.read_parquet(dataset)["liquidation_risk"].mean())
    base = result.predictions.loc[result.predictions["candidate"].eq("base_rate")]
    assert base["prediction"].eq(expected_rate).all()


def test_rejects_source_metadata_with_execution_authority(tmp_path: Path) -> None:
    """An installed source model cannot be scored as observe-only evidence."""
    report, dataset, model_dir = _frozen_evidence(tmp_path)
    metadata_path = model_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["installed"] = True
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata contract differs"):
        score_frozen_source_challengers(
            _rows(70, offset=1_000),
            training_report_path=report,
            training_dataset_path=dataset,
            model_dir=model_dir,
        )


def test_acceptance_requires_all_predeclared_thresholds() -> None:
    """One good ranking metric cannot pass the frozen acceptance contract."""
    metrics: dict[str, dict[str, float | int | None]] = {
        "base_rate": {"log_loss": 0.50, "roc_auc": 0.50, "top_quintile_lift": None},
        "lightgbm_base": {
            "log_loss": 0.48,
            "roc_auc": 0.55,
            "top_quintile_lift": 1.1,
        },
        "logistic_source_state": {
            "log_loss": 0.47,
            "roc_auc": 0.61,
            "top_quintile_lift": 1.4,
        },
        "lightgbm_source_state": {
            "log_loss": 0.46,
            "roc_auc": 0.61,
            "top_quintile_lift": 1.6,
        },
        "lightgbm_source_sequence": {
            "log_loss": 0.49,
            "roc_auc": 0.70,
            "top_quintile_lift": 2.0,
        },
    }

    result = source_candidate_acceptance(metrics)

    assert result["lightgbm_source_state"]["passed"] is True
    assert result["logistic_source_state"]["passed"] is False
    assert result["lightgbm_source_sequence"]["passed"] is False
