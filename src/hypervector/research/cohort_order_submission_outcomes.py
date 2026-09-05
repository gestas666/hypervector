"""Exact venue order-submission outcomes from cohort asset ledgers."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_live_audit_values import payload, positive_int, text

Record = Mapping[str, object]
_OUTCOME_EVENT_TYPES = frozenset(
    {"order_acknowledgement", "stop_order", "target_order", "close"}
)


@dataclass(frozen=True)
class SubmissionOutcome:
    """One validated normalized venue acknowledgement."""

    event_type: str
    operation: str
    accepted: bool
    status: str
    error: str | None


def build_order_submission_outcomes(
    assets: Mapping[str, Sequence[Record]], *, scope: str
) -> dict[str, object]:
    """Summarize every exact normalized order outcome in an asset-ledger scope."""
    scope_name = text(scope, "submission outcome scope")
    outcomes = tuple(_outcomes(assets))
    accepted = sum(outcome.accepted for outcome in outcomes)
    return {
        "scope": scope_name,
        "status": "measured" if outcomes else "measured_zero",
        "outcomes": len(outcomes),
        "accepted": accepted,
        "rejected": len(outcomes) - accepted,
        "source_events": dict(
            sorted(Counter(row.event_type for row in outcomes).items())
        ),
        "by_operation": _by_operation(outcomes),
        "rejection_reasons": dict(
            sorted(Counter(row.error for row in outcomes if not row.accepted).items())
        ),
    }


def _outcomes(assets: Mapping[str, Sequence[Record]]) -> list[SubmissionOutcome]:
    output: list[SubmissionOutcome] = []
    for rows in assets.values():
        for row in rows:
            event_type = row.get("event_type")
            if event_type not in _OUTCOME_EVENT_TYPES:
                continue
            values = payload(row)
            if "accepted" not in values:
                continue
            output.append(_outcome(text(event_type, "outcome event type"), values))
    return output


def _outcome(event_type: str, values: Record) -> SubmissionOutcome:
    accepted = values.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError("order outcome accepted must be boolean")
    if accepted:
        positive_int(values.get("oid"), "accepted order outcome oid")
    error = values.get("error")
    if not accepted:
        error = text(error, "rejected order outcome error")
    elif error is not None:
        raise ValueError("accepted order outcome cannot contain an error")
    return SubmissionOutcome(
        event_type=event_type,
        operation=text(values.get("operation"), "order outcome operation"),
        accepted=accepted,
        status=text(values.get("status"), "order outcome status"),
        error=error,
    )


def _by_operation(
    outcomes: Sequence[SubmissionOutcome],
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[SubmissionOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.operation].append(outcome)
    return {
        operation: _operation_summary(rows)
        for operation, rows in sorted(grouped.items())
    }


def _operation_summary(outcomes: Sequence[SubmissionOutcome]) -> dict[str, object]:
    accepted = sum(outcome.accepted for outcome in outcomes)
    return {
        "outcomes": len(outcomes),
        "accepted": accepted,
        "rejected": len(outcomes) - accepted,
        "by_status": dict(sorted(Counter(row.status for row in outcomes).items())),
    }
