"""Numeric identity tolerance for immutable regime annotations."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.data.research_database import ResearchDatabase
from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
)


def _write_labels(path: Path, metadata: Path, volume_ratio: float) -> None:
    labels = pd.DataFrame(
        {
            "available_at": [pd.Timestamp("2026-07-28T00:05:00Z")],
            "primary_code": ["RANGE"],
            "secondary_code": [None],
            "confidence": [0.8],
            "raw_primary_code": ["RANGE"],
            "raw_secondary_code": [None],
            "raw_confidence": [0.9],
            "volume_ratio": [volume_ratio],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-07-28T00:00:00Z")]),
    )
    labels.to_parquet(path)
    metadata.write_text(
        json.dumps(
            {
                "upstream_revision": PINNED_HYPERTRADER_REVISION,
                "report_only": True,
                "runtime_strategy_changed": False,
                "model_authority": "observe",
                "output": file_evidence(path),
            }
        ),
        encoding="utf-8",
    )


def test_annotation_reimport_accepts_machine_precision_ratio_delta(
    tmp_path: Path,
) -> None:
    database = ResearchDatabase(tmp_path / "research.duckdb")
    labels = tmp_path / "labels.parquet"
    metadata = tmp_path / "labels.json"
    _write_labels(labels, metadata, 1.2)
    database.ingest_hypertrader_labels(labels, metadata)
    _write_labels(labels, metadata, 1.2 + 3e-13)

    report = database.ingest_hypertrader_labels(labels, metadata)

    assert report.imported_labels == 0
    assert report.skipped_labels == 1


def test_annotation_reimport_rejects_material_ratio_delta(tmp_path: Path) -> None:
    database = ResearchDatabase(tmp_path / "research.duckdb")
    labels = tmp_path / "labels.parquet"
    metadata = tmp_path / "labels.json"
    _write_labels(labels, metadata, 1.2)
    database.ingest_hypertrader_labels(labels, metadata)
    _write_labels(labels, metadata, 1.201)

    with pytest.raises(ValueError, match="conflicting Hypertrader annotation"):
        database.ingest_hypertrader_labels(labels, metadata)
