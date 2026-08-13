"""Frozen-model holdout scoring tests for Hypervelocity challengers."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.ml.hypervelocity_challenger import train_annotation_only_challengers
from hypervector.ml.hypervelocity_challenger_holdout import score_frozen_challengers
from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
)


def _rows(n_rows: int, *, offset: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(42 + offset)
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
    for name in BASE_FEATURE_NAMES + BOOK_FEATURE_NAMES + SEQUENCE_BOOK_FEATURE_NAMES:
        frame[name] = rng.normal(size=n_rows) + labels * 0.1
    return frame


def _frozen_evidence(tmp_path: Path) -> tuple[Path, Path, Path]:
    training = _rows(180)
    model_dir = tmp_path / "models"
    result = train_annotation_only_challengers(training, model_dir)
    dataset = tmp_path / "dataset.parquet"
    training.to_parquet(dataset, index=False)
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "ok": True,
                "report_only": True,
                "runtime_strategy_changed": False,
                "model_evidence": {
                    name: file_evidence(path)
                    for name, path in result.model_paths.items()
                },
                "data_evidence": {"dataset": file_evidence(dataset)},
            }
        ),
        encoding="utf-8",
    )
    return report, dataset, model_dir


def test_scores_frozen_models_without_modifying_their_evidence(tmp_path: Path) -> None:
    """Holdout predictions use the exact persisted models and training base rate."""
    report, dataset, model_dir = _frozen_evidence(tmp_path)
    before = {path.name: file_evidence(path) for path in model_dir.iterdir()}

    result = score_frozen_challengers(
        _rows(70, offset=1_000),
        training_report_path=report,
        training_dataset_path=dataset,
        model_dir=model_dir,
    )

    after = {path.name: file_evidence(path) for path in model_dir.iterdir()}
    assert before == after
    assert len(result.metrics) == 8
    assert result.metrics["base_rate"]["samples"] == 70
    assert result.predictions["candidate"].nunique() == 8
    expected_rate = float(pd.read_parquet(dataset)["liquidation_risk"].mean())
    base = result.predictions.loc[result.predictions["candidate"].eq("base_rate")]
    assert base["prediction"].eq(expected_rate).all()


def test_rejects_metadata_that_claims_runtime_installation(tmp_path: Path) -> None:
    """A model carrying execution authority cannot masquerade as a challenger."""
    report, dataset, model_dir = _frozen_evidence(tmp_path)
    metadata_path = model_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["installed"] = True
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata contract differs"):
        score_frozen_challengers(
            _rows(70, offset=1_000),
            training_report_path=report,
            training_dataset_path=dataset,
            model_dir=model_dir,
        )
