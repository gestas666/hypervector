"""Prospective observer-record scoping shared by lifecycle diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    nonnegative_int,
    object_list,
    payload,
    timestamp,
)

Record = Mapping[str, object]


def prospective_observer_records(
    records: Sequence[Record],
    prospective_start_ms: int,
    *,
    label: str,
) -> tuple[Record, ...]:
    """Retain identities while excluding observations and evaluations before start."""
    start_ms = _prospective_start(prospective_start_ms, label)
    output: list[Record] = []
    for row in records:
        if row.get("event_type") == "configuration_identity":
            output.append(row)
            continue
        if int(timestamp(row).timestamp() * 1_000) < start_ms:
            continue
        output.append(_prospective_evaluations(row, start_ms))
    return tuple(output)


def _prospective_start(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} prospective start must be a nonnegative integer")
    return value


def _prospective_evaluations(row: Record, start_ms: int) -> Record:
    values = payload(row)
    if "evaluations" not in values:
        return row
    evaluations = [
        value
        for value in object_list(values, "evaluations", required=False)
        if nonnegative_int(value.get("decision_time_ms"), "decision time") >= start_ms
    ]
    return {**row, "payload": {**values, "evaluations": evaluations}}
