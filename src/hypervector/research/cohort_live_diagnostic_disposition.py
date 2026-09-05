"""Reconcile live one-blocker diagnostics with closed research decisions."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.cohort_hypothesis_ledger import (
    normalize_hypothesis_decisions,
)

Record = Mapping[str, object]


def apply_closed_path_dispositions(
    routes: list[dict[str, object]], decisions: object
) -> list[dict[str, object]]:
    """Copy routes while closing explicitly bound diagnostic blockers."""
    dispositions = _disposition_index(decisions)
    output: list[dict[str, object]] = []
    for route in routes:
        route_name = _text(route.get("route"), "diagnostic route")
        paths = [
            _apply_to_path(route_name, path, dispositions)
            for path in _records(route.get("one_blocker_paths"), "diagnostic paths")
        ]
        output.append({**route, "one_blocker_paths": paths})
    return output


def _disposition_index(decisions: object) -> dict[tuple[str, str], Record]:
    index: dict[tuple[str, str], Record] = {}
    for row in normalize_hypothesis_decisions(decisions):
        route = _text(row.get("route"), "hypothesis route")
        blockers = row.get("closed_live_diagnostic_blockers", [])
        if not isinstance(blockers, list):
            raise ValueError("closed diagnostic blockers must be an array")
        for blocker in blockers:
            key = (route, _text(blocker, "closed diagnostic blocker"))
            if key in index:
                raise ValueError("duplicate closed live diagnostic disposition")
            index[key] = row
    return index


def _apply_to_path(
    route: str, path: Record, dispositions: Mapping[tuple[str, str], Record]
) -> dict[str, object]:
    blocker = _text(path.get("blocker"), "diagnostic blocker")
    decision = dispositions.get((route, blocker))
    if decision is None:
        return dict(path)
    return {
        **path,
        "raw_assessment": path.get("assessment"),
        "assessment": "closed_by_hypothesis_decision",
        "hypothesis_disposition": {
            key: decision.get(key)
            for key in (
                "hypothesis_id",
                "status",
                "decision_source",
                "reopen_condition",
            )
        },
    }


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
