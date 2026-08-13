"""Prospective report-only tracking for the inactive v32 route authority."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hypervector.research.route_forward_spec import V32_ROUTE_FORWARD_SPEC
from hypervector.research.v31_route_forward import (
    build_candidate_route_forward_snapshot,
)

Record = Mapping[str, object]

REMOVED_ROUTES = V32_ROUTE_FORWARD_SPEC.removed_routes
RETAINED_CONTROL_ROUTES = V32_ROUTE_FORWARD_SPEC.retained_control_routes


def build_v32_route_forward_snapshot(
    checkpoint: Record,
    journal: Record,
    source_path: Path,
    candidate_path: Path,
) -> dict[str, object]:
    """Build one strict v25/v32 route-forward evidence snapshot."""
    return build_candidate_route_forward_snapshot(
        checkpoint,
        journal,
        source_path,
        candidate_path,
        spec=V32_ROUTE_FORWARD_SPEC,
    )
