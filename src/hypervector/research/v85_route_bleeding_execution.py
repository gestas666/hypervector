"""Submission and fill-size validation for the V85 route audit."""

from __future__ import annotations

from collections.abc import Mapping


Record = Mapping[str, object]
JsonObject = dict[str, object]


def submission_reconciliation(execution: Record) -> JsonObject:
    """Validate and project accepted and rejected submission outcomes."""
    raw = execution.get("current_run_submission_outcomes")
    if raw is None:
        return {
            "outcomes": 0,
            "accepted": 0,
            "rejected": 0,
            "rejection_reasons": {},
        }
    values = _mapping(raw, "current-run submission outcomes")
    outcomes = _count(values.get("outcomes"), "submission outcomes")
    accepted = _count(values.get("accepted"), "accepted submissions")
    rejected = _count(values.get("rejected"), "rejected submissions")
    reasons = _reason_counts(values.get("rejection_reasons", {}))
    if accepted + rejected != outcomes or sum(reasons.values()) != rejected:
        raise ValueError("submission outcome counts are inconsistent")
    return {
        "outcomes": outcomes,
        "accepted": accepted,
        "rejected": rejected,
        "rejection_reasons": reasons,
    }


def lifecycle_size_matches(row: Record) -> bool:
    """Return whether one reflected closed lifecycle has equal entry/exit size."""
    entry = row.get("entry")
    exit_fill = row.get("exit")
    if not isinstance(entry, Mapping) or not isinstance(exit_fill, Mapping):
        return True
    entry_size = entry.get("size")
    exit_size = exit_fill.get("size")
    if entry_size is None or exit_size is None:
        return True
    left = _number(entry_size, "entry size")
    right = _number(exit_size, "exit size")
    return abs(left - right) <= max(abs(left), abs(right), 1.0) * 1e-9


def closed_lifecycle_missing_fields(row: Record) -> list[str]:
    """List absent top-level evidence needed for economic reconciliation."""
    missing = [
        field
        for field in ("entry", "exit", "protective_stop", "completed_hold_capture")
        if not isinstance(row.get(field), Mapping)
    ]
    hold = row.get("completed_hold_capture")
    if isinstance(hold, Mapping) and hold.get("status") != "resolved":
        missing.append("completed_hold_capture.status")
    for field in ("net_pnl_usd", "fees_usd", "funding_usd"):
        if not _is_number(row.get(field)):
            missing.append(field)
    return missing


def _reason_counts(value: object) -> dict[str, int]:
    rows = _mapping(value, "submission rejection reasons")
    result: dict[str, int] = {}
    for reason, count in rows.items():
        if not isinstance(reason, str) or not reason:
            raise ValueError("submission rejection reason must be non-empty")
        result[reason] = _count(count, "submission rejection count")
    return dict(sorted(result.items()))


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if not _is_number(value):
        raise ValueError(f"{label} must be finite numeric")
    return float(value)


def _is_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    result = float(value)
    return result == result and result not in {float("inf"), float("-inf")}
