"""Durable report-only hypothesis lifecycle reconciliation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

Record = Mapping[str, object]

_CLOSED_STATUSES = frozenset({"accepted", "rejected", "deferred", "superseded"})


def merge_hypothesis_ledger(
    active: Sequence[Record],
    historical: object,
) -> list[dict[str, object]]:
    """Merge active hypotheses with immutable closed research decisions."""
    active_rows = [_normalized_active(row) for row in active]
    closed_rows = normalize_hypothesis_decisions(historical)
    _require_unique_identities(active_rows + closed_rows)
    _require_no_reopened_experiment(active_rows, closed_rows)
    _require_valid_successors(active_rows, closed_rows)
    return active_rows + closed_rows


def normalize_hypothesis_decisions(value: object) -> list[dict[str, object]]:
    """Validate and normalize source-bound closed hypothesis decisions."""
    return [_normalized_decision(row) for row in _records(value)]


def normalize_active_hypotheses(value: object) -> list[dict[str, object]]:
    """Validate and normalize source-bound active research hypotheses."""
    return [_normalized_active(row) for row in _records(value)]


def _normalized_active(row: Record) -> dict[str, object]:
    if row.get("status") != "being_tested":
        raise ValueError("active hypothesis status must be being_tested")
    if row.get("execution_effect") != "report_only":
        raise ValueError("active hypothesis must be report-only")
    return dict(row)


def _normalized_decision(row: Record) -> dict[str, object]:
    status = _text(row.get("status"), "hypothesis decision status")
    if status not in _CLOSED_STATUSES:
        raise ValueError(f"unsupported closed hypothesis status: {status}")
    reopen = _optional_text(row.get("reopen_condition"), "reopen condition")
    successor = _optional_text(row.get("superseded_by"), "superseded by")
    if status in {"rejected", "deferred"} and reopen is None:
        raise ValueError(f"{status} hypothesis requires a reopen condition")
    if status == "superseded" and successor is None:
        raise ValueError("superseded hypothesis requires a successor")
    output: dict[str, object] = {
        "hypothesis_id": _text(row.get("hypothesis_id"), "hypothesis identity"),
        "route": _text(row.get("route"), "hypothesis route"),
        "status": status,
        "experiment": _text(row.get("experiment"), "hypothesis experiment"),
        "decision_reason": _text(row.get("decision_reason"), "decision reason"),
        "decision_source": _text(row.get("decision_source"), "decision source"),
        "reopen_condition": reopen,
        "superseded_by": successor,
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }
    blockers = _optional_text_list(
        row.get("closed_live_diagnostic_blockers"), "closed diagnostic blockers"
    )
    if blockers:
        output["closed_live_diagnostic_blockers"] = blockers
    return output


def _require_unique_identities(rows: Sequence[Record]) -> None:
    identities = [
        _text(row.get("hypothesis_id"), "hypothesis identity") for row in rows
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate hypothesis identity")


def _require_no_reopened_experiment(
    active: Sequence[Record],
    closed: Sequence[Record],
) -> None:
    closed_pairs = {
        (
            _text(row.get("route"), "closed hypothesis route"),
            _text(row.get("experiment"), "closed hypothesis experiment"),
        )
        for row in closed
    }
    for row in active:
        pair = (
            _text(row.get("route"), "active hypothesis route"),
            _text(row.get("experiment"), "active hypothesis experiment"),
        )
        if pair in closed_pairs:
            raise ValueError("current research reopens a closed hypothesis")


def _require_valid_successors(
    active: Sequence[Record],
    closed: Sequence[Record],
) -> None:
    known_ids = {
        _text(row.get("hypothesis_id"), "hypothesis identity")
        for row in [*active, *closed]
    }
    for row in closed:
        successor = row.get("superseded_by")
        if row.get("status") == "superseded" and successor not in known_ids:
            raise ValueError("superseded hypothesis does not name a known successor")
    successors = {
        _text(row.get("hypothesis_id"), "hypothesis identity"): _text(
            row.get("superseded_by"), "superseded by"
        )
        for row in closed
        if row.get("status") == "superseded"
    }
    for origin in successors:
        seen: set[str] = set()
        current = origin
        while current in successors:
            if current in seen:
                raise ValueError("hypothesis successor cycle")
            seen.add(current)
            current = successors[current]


def _records(value: object) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError("historical hypotheses must be an array of objects")
    return list(value)


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _optional_text_list(value: object, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    result = [_text(item, label) for item in value]
    if result != sorted(set(result)):
        raise ValueError(f"{label} must be sorted and unique")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
