"""Hash-chained material-change journal for v32 route evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hypervector.research.v31_route_change_journal import (
    RouteChangeJournalSpec,
    append_route_material_change,
)

Record = Mapping[str, object]

V32_CHANGE_JOURNAL_SPEC = RouteChangeJournalSpec(
    label="v32",
    snapshot_schema="v32_route_forward_snapshot_v1",
    event_schema="v32_route_material_change_v1",
)


def append_v32_material_change(path: Path, snapshot: Record) -> bool:
    """Append one state only when material v32 evidence changed."""
    return append_route_material_change(path, snapshot, V32_CHANGE_JOURNAL_SPEC)
