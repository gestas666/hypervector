"""Atomic display bundle for independently refreshed opportunity observers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_live_checkpoint import (
    merge_opportunity_matrices,
)


def publish_opportunity_matrix_bundle(
    primary_path: Path,
    supplemental_paths: Sequence[Path],
    destination: Path,
) -> dict[str, object]:
    """Validate current observer files and atomically publish one TUI input."""
    primary = _load_mapping(primary_path, label="primary opportunity matrix")
    supplemental = [
        _load_mapping(path, label="supplemental opportunity matrix")
        for path in supplemental_paths
    ]
    bundled = merge_opportunity_matrices(primary, supplemental)
    write_atomic_json(destination, bundled)
    return bundled


def _load_mapping(path: Path, *, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value
