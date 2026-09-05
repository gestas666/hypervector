"""Structured terminal events for the report-only improvement monitor."""

from __future__ import annotations

from collections.abc import Mapping
import json
import sys

Record = Mapping[str, object]


def emit_success(report: Record) -> None:
    """Emit one compact successful monitor-refresh event."""
    assessment = _mapping(report.get("assessment"), "improvement assessment")
    performance = _mapping(report.get("performance"), "improvement performance")
    print(
        json.dumps(
            {
                "event": "cohort_improvement_digest",
                "state": "published",
                "closed_trades": performance.get("closed_trades"),
                "top_research_priority": assessment.get("top_research_priority"),
                "execution_authority": "none",
            },
            sort_keys=True,
        ),
        flush=True,
    )


def emit_failure(exc: Exception) -> None:
    """Emit one compact fail-closed monitor-refresh event."""
    print(
        json.dumps(
            {
                "event": "cohort_improvement_digest",
                "state": "unavailable",
                "technical_issue": f"{type(exc).__name__}: {exc}",
                "execution_authority": "none",
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value
