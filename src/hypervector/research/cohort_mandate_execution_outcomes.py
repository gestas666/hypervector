"""Fail-closed order-rejection evidence for the continuous mandate."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]


def mandate_order_rejections(
    execution: Record, routing_actions: int
) -> dict[str, object]:
    """Return measured rejections or an explicit legacy evidence limitation."""
    raw = execution.get("current_run_submission_outcomes")
    if raw is None:
        return _legacy_projection(routing_actions)
    summary = _mapping(raw, "current-run submission outcomes")
    if summary.get("scope") != "current_run":
        raise ValueError("submission outcomes must use current_run scope")
    outcomes = _nonnegative_int(summary.get("outcomes"), "submission outcomes")
    accepted = _nonnegative_int(summary.get("accepted"), "accepted outcomes")
    rejected = _nonnegative_int(summary.get("rejected"), "rejected outcomes")
    if accepted + rejected != outcomes:
        raise ValueError("submission outcome counts disagree")
    expected_status = "measured" if outcomes else "measured_zero"
    if summary.get("status") != expected_status:
        raise ValueError("submission outcome status disagrees with its population")
    operations = _validated_operations(summary, outcomes, accepted, rejected)
    reasons = _validated_reasons(summary, rejected)
    return {
        "status": "measured",
        "count": rejected,
        "routing_actions": routing_actions,
        "observed_submission_outcomes": outcomes,
        "accepted_submission_outcomes": accepted,
        "by_operation": operations,
        "rejection_reasons": reasons,
    }


def _legacy_projection(actions: int) -> dict[str, object]:
    if actions == 0:
        return {
            "status": "measured_no_submission_attempts",
            "count": 0,
            "submission_capable_actions": 0,
        }
    return {
        "status": "unavailable_submission_outcomes_not_projected",
        "count": None,
        "submission_capable_actions": actions,
    }


def _validated_operations(
    summary: Record, outcomes: int, accepted: int, rejected: int
) -> dict[str, dict[str, object]]:
    raw = _mapping(summary.get("by_operation"), "submission operations")
    result = {
        _text(key, "submission operation"): _validated_operation(value)
        for key, value in raw.items()
    }
    totals = tuple(
        sum(
            _nonnegative_int(row.get(key), f"operation {key}")
            for row in result.values()
        )
        for key in ("outcomes", "accepted", "rejected")
    )
    if totals != (outcomes, accepted, rejected):
        raise ValueError("submission operation counts disagree")
    return dict(sorted(result.items()))


def _validated_operation(value: object) -> dict[str, object]:
    row = _mapping(value, "submission operation summary")
    outcomes = _nonnegative_int(row.get("outcomes"), "operation outcomes")
    accepted = _nonnegative_int(row.get("accepted"), "operation accepted")
    rejected = _nonnegative_int(row.get("rejected"), "operation rejected")
    statuses = {
        _text(status, "submission status"): _nonnegative_int(count, "status count")
        for status, count in _mapping(row.get("by_status"), "outcome statuses").items()
    }
    if accepted + rejected != outcomes or sum(statuses.values()) != outcomes:
        raise ValueError("submission operation summary is inconsistent")
    return {
        "outcomes": outcomes,
        "accepted": accepted,
        "rejected": rejected,
        "by_status": dict(sorted(statuses.items())),
    }


def _validated_reasons(summary: Record, rejected: int) -> dict[str, int]:
    raw = _mapping(summary.get("rejection_reasons"), "rejection reasons")
    result = {
        _text(reason, "rejection reason"): _nonnegative_int(count, "reason count")
        for reason, count in raw.items()
    }
    if sum(result.values()) != rejected:
        raise ValueError("submission rejection reason counts disagree")
    return dict(sorted(result.items()))


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
