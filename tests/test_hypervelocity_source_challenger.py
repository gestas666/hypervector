"""Purged source-state challenger tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.ml.hypervelocity_source_challenger import (
    SOURCE_CANDIDATE_NAMES,
    train_source_state_challengers,
)
from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
)
from hypervector.research.hypervelocity_source_features import SOURCE_FEATURE_NAMES


def _rows(n_rows: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    signal = np.arange(n_rows, dtype=np.int64) * 3_600_000
    labels = (np.arange(n_rows) % 8 == 0).astype(int)
    rows = pd.DataFrame(
        {
            "lifecycle_id": np.arange(n_rows),
            "segment_id": np.where(np.arange(n_rows) < 120, "a", "b"),
            "signal_ts_ms": signal,
            "outcome_ts_ms": signal + 600_000,
            "liquidation_risk": labels,
        }
    )
    names = (
        BASE_FEATURE_NAMES
        + BOOK_FEATURE_NAMES
        + SEQUENCE_BOOK_FEATURE_NAMES
        + SOURCE_FEATURE_NAMES
    )
    for name in names:
        rows[name] = rng.normal(size=n_rows) + 0.2 * labels
    return rows


def test_source_challengers_share_five_folds_and_remain_uninstalled(
    tmp_path: Path,
) -> None:
    """The predeclared source family uses identical OOS rows and no authority."""
    result = train_source_state_challengers(_rows(), tmp_path / "models")

    assert tuple(result.metrics) == SOURCE_CANDIDATE_NAMES
    assert all(item["folds_used"] == 5 for item in result.metrics.values())
    assert result.predictions["candidate"].nunique() == len(SOURCE_CANDIDATE_NAMES)
    assert result.predictions["segment_id"].notna().all()
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["installed"] is False
    assert metadata["decision_policy"] == "annotation_only"
    assert metadata["source_features"] == list(SOURCE_FEATURE_NAMES)
    assert metadata["development_end_utc"] == "2026-01-09T00:00:00+00:00"
    assert all(path.is_file() for path in result.model_paths.values())
