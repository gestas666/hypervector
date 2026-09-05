"""Research availability while an identity-bound transition drain holds entries."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]

_ENTRY_DEPENDENT_EXPERIMENTS = frozenset(
    {
        "collect_both_side_live_execution",
        "collect_route_specific_regime_context_evidence",
        "collect_side_specific_evidence",
    }
)


def transition_drain_holds_entries(checkpoint: Record) -> bool:
    """Return whether the checkpoint proves new-entry collection is disabled."""
    raw = checkpoint.get("transition_drain")
    if raw is None:
        return False
    if not isinstance(raw, Mapping):
        raise ValueError("transition drain must be an object")
    status = raw.get("status")
    if not isinstance(status, str) or not status.strip():
        raise ValueError("transition drain status must be non-empty text")
    if status not in {"inactive", "active", "completed"}:
        raise ValueError(f"unsupported transition drain status: {status}")
    return status in {"active", "completed"}


def with_research_availability(
    queue: list[dict[str, object]], drain_active: bool
) -> list[dict[str, object]]:
    """Mark entry-dependent investigations unavailable during an active drain."""
    output = []
    for row in queue:
        experiment = row.get("next_experiment")
        if not isinstance(experiment, str) or not experiment.strip():
            raise ValueError("next experiment must be non-empty text")
        suspended = drain_active and experiment in _ENTRY_DEPENDENT_EXPERIMENTS
        output.append(
            dict(
                row,
                research_availability=(
                    "suspended_by_transition_drain"
                    if suspended
                    else "available_report_only"
                ),
            )
        )
    return output


def build_research_assessment(
    source: object,
    ranking: list[dict[str, object]],
    queue: list[dict[str, object]],
    drain_active: bool,
) -> dict[str, object]:
    """Reconcile summary priority with the investigations actually available."""
    if source is not None and not isinstance(source, Mapping):
        raise ValueError("research assessment must be an object")
    result = {} if source is None else dict(source)
    available = sum(
        row.get("research_availability") == "available_report_only" for row in queue
    )
    result.update(
        {
            "automatic_action": "none",
            "queued_experiments": available,
            "total_experiments": len(queue),
            "suspended_experiments": len(queue) - available,
            "top_research_priority": ranking[0]["route"] if ranking else None,
            "recommendation": (
                "execute_available_report_only_experiments_during_drain"
                if drain_active
                else "execute_ranked_report_only_experiments_then_review"
            ),
        }
    )
    return result
