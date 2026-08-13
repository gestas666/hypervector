"""Bind generated Hypertrader labels to immutable source metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence


@dataclass(frozen=True)
class HypertraderLabelEvidence:
    """Verified identity for one label parquet and its classifier revision."""

    revision: str
    metadata_verified: bool
    files: dict[str, object]


def load_label_evidence(
    labels_path: Path,
    metadata_path: Path | None,
) -> HypertraderLabelEvidence:
    """Verify optional generation metadata against the exact label parquet."""
    labels = file_evidence(labels_path)
    if metadata_path is None:
        return HypertraderLabelEvidence(
            revision="unverified",
            metadata_verified=False,
            files={"labels": labels},
        )
    payload = _metadata_payload(metadata_path)
    revision = payload.get("upstream_revision")
    expected = payload.get("output")
    if not isinstance(revision, str) or not revision:
        raise ValueError("label metadata is missing upstream_revision")
    if not isinstance(expected, dict) or expected != labels:
        raise ValueError("label parquet does not match metadata output evidence")
    return HypertraderLabelEvidence(
        revision=revision,
        metadata_verified=True,
        files={"labels": labels, "metadata": file_evidence(metadata_path)},
    )


def _metadata_payload(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"label metadata is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("label metadata must contain a JSON object")
    return payload
