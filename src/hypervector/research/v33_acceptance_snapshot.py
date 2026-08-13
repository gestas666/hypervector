"""Exact identity snapshot for inactive v33 post-start acceptance tooling."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hypervector.research.candidate_acceptance_snapshot import (
    build_candidate_acceptance_snapshot,
)
from hypervector.research.v33_acceptance import V33_ACCEPTANCE_SPEC

Record = Mapping[str, object]


def build_v33_acceptance_snapshot(
    checkpoint: Record,
    journal: Record,
    candidate_path: Path,
) -> dict[str, object]:
    """Return a report-only snapshot bound to exact v33 authority."""
    return build_candidate_acceptance_snapshot(
        checkpoint,
        journal,
        candidate_path,
        spec=V33_ACCEPTANCE_SPEC,
    )
