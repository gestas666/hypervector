"""Evidence contracts for replaying labels from historical source revisions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hypertrader_label_evidence import load_label_evidence


def test_label_metadata_binds_revision_to_exact_parquet(tmp_path: Path) -> None:
    labels = tmp_path / "labels.parquet"
    pd.DataFrame({"value": [1]}).to_parquet(labels)
    metadata = tmp_path / "labels.json"
    metadata.write_text(
        json.dumps(
            {
                "upstream_revision": "legacy-revision",
                "output": file_evidence(labels),
            }
        )
    )

    evidence = load_label_evidence(labels, metadata)

    assert evidence.revision == "legacy-revision"
    assert evidence.metadata_verified is True


def test_label_metadata_rejects_parquet_drift(tmp_path: Path) -> None:
    labels = tmp_path / "labels.parquet"
    pd.DataFrame({"value": [1]}).to_parquet(labels)
    metadata = tmp_path / "labels.json"
    metadata.write_text(
        json.dumps(
            {
                "upstream_revision": "legacy-revision",
                "output": file_evidence(labels),
            }
        )
    )
    pd.DataFrame({"value": [2]}).to_parquet(labels)

    with pytest.raises(ValueError, match="label parquet does not match metadata"):
        load_label_evidence(labels, metadata)
