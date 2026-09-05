"""Validated cumulative telemetry for the report-only MU decision journal."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from hypervector.live.hip3_shadow_candle_storage import jsonl_rows


def mu_shadow_journal_event_ids(
    path: Path,
    *,
    expected_event_type: str = "mu_hip3_breakout_shadow_decision",
) -> set[str]:
    """Return exact unique event identities from one route-bound journal."""
    return {
        _text(row.get("event_id"), "event_id")
        for row in _validated_rows(path, expected_event_type)
    }


def mu_shadow_journal_summary(
    path: Path,
    *,
    expected_event_type: str = "mu_hip3_breakout_shadow_decision",
) -> dict[str, object]:
    """Summarize one exact route journal without execution authority."""
    decisions = tuple(
        _object(row.get("decision"), "decision")
        for row in _validated_rows(path, expected_event_type)
    )
    sides = [decision.get("side") for decision in decisions]
    if any(side not in (None, "long", "short") for side in sides):
        raise ValueError("MU shadow journal decision side is invalid")
    if any(not isinstance(decision.get("eligible"), bool) for decision in decisions):
        raise ValueError("MU shadow journal eligibility is invalid")
    return {
        "decision_rows_total": len(decisions),
        "eligible_decisions_total": sum(
            decision["eligible"] is True for decision in decisions
        ),
        "long_decisions_total": sides.count("long"),
        "short_decisions_total": sides.count("short"),
        "non_action_decisions_total": sides.count(None),
        "last_decision_time_ms": _last_decision_time(decisions),
    }


def _validated_rows(
    path: Path,
    expected_event_type: str,
) -> tuple[dict[str, object], ...]:
    if not path.exists():
        return ()
    rows = jsonl_rows(path, "MU shadow journal")
    event_ids = [_text(row.get("event_id"), "event_id") for row in rows]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("MU shadow journal contains a duplicate event")
    for row in rows:
        if row.get("event_type") != expected_event_type:
            raise ValueError("MU shadow journal event type is invalid")
        if row.get("execution_authority") != "none" or row.get("intents") != []:
            raise ValueError("MU shadow journal authority is invalid")
    return rows


def _last_decision_time(decisions: tuple[dict[str, object], ...]) -> int | None:
    if not decisions:
        return None
    value = decisions[-1].get("decision_time_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("MU shadow journal last decision time is invalid")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"MU shadow journal {label} must be an object")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"MU shadow journal {label} must be non-empty text")
    return value
