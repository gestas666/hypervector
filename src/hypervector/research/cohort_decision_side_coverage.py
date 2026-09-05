"""Validate decision-side coverage in live opportunity diagnostics."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]


def build_decision_side_coverage(
    outcomes: Record, evaluations: int, eligible: int
) -> dict[str, object]:
    """Report exact long/short coverage or an explicit legacy absence."""
    raw_value = outcomes.get("by_side")
    if raw_value is None:
        return _unavailable_coverage()
    raw = _mapping(raw_value, "decision sides")
    if set(raw).difference({"long", "short"}):
        raise ValueError("decision sides must be long or short")
    by_side = {side: _side_record(side, row) for side, row in sorted(raw.items())}
    directional = sum(row["evaluations"] for row in by_side.values())
    nondirectional = _nonnegative_int(
        outcomes.get("no_direction"), "nondirectional evaluations"
    )
    if directional + nondirectional != evaluations:
        raise ValueError("decision side evaluations do not reconcile")
    if sum(row["eligible_evaluations"] for row in by_side.values()) != eligible:
        raise ValueError("decision side eligibility does not reconcile")
    observed = [side for side, row in by_side.items() if row["evaluations"]]
    eligible_sides = [
        side for side, row in by_side.items() if row["eligible_evaluations"]
    ]
    return {
        "status": "available",
        "by_side": by_side,
        "directional_evaluations": directional,
        "nondirectional_evaluations": nondirectional,
        "observed_sides": observed,
        "eligible_sides": eligible_sides,
        "both_sides_observed": observed == ["long", "short"],
    }


def _side_record(side: str, value: object) -> dict[str, int]:
    row = _mapping(value, f"decision side {side}")
    evaluations = _nonnegative_int(row.get("evaluations"), "side evaluations")
    eligible = _nonnegative_int(
        row.get("eligible_evaluations"), "side eligible evaluations"
    )
    if eligible > evaluations:
        raise ValueError("side eligible evaluations exceed side evaluations")
    return {"evaluations": evaluations, "eligible_evaluations": eligible}


def _unavailable_coverage() -> dict[str, object]:
    return {
        "status": "unavailable_legacy_audit",
        "by_side": {},
        "directional_evaluations": None,
        "nondirectional_evaluations": None,
        "observed_sides": [],
        "eligible_sides": [],
        "both_sides_observed": False,
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
