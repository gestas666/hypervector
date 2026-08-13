"""Exact identity snapshot for inactive v32 post-start acceptance tooling."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hypervector.research.candidate_acceptance_snapshot import (
    build_candidate_acceptance_snapshot,
)
from hypervector.research.v32_acceptance import V32_ACCEPTANCE_SPEC

Record = Mapping[str, object]


def build_v32_acceptance_snapshot(
    checkpoint: Record,
    journal: Record,
    candidate_path: Path,
) -> dict[str, object]:
    """Return a report-only snapshot bound to exact v32 authority."""
    return build_candidate_acceptance_snapshot(
        checkpoint,
        journal,
        candidate_path,
        spec=V32_ACCEPTANCE_SPEC,
    )
