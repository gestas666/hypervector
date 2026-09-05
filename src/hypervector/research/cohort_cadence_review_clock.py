"""Report-only cadence review clock for a live cohort prefix."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)

Record = Mapping[str, object]


def build_monitored_improvement_report(
    checkpoint: Record, digest: Record
) -> dict[str, object]:
    """Build the base report and attach a configured cadence-review clock."""
    report = build_continuous_improvement_report(checkpoint, digest)
    overrides = _mapping(
        digest.get("research_decision_overrides"), "research decision overrides"
    )
    if not overrides.get("review_triggers"):
        return report
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    return attach_cadence_review_clock(report, audit, overrides)


def attach_cadence_review_clock(
    report: Record, audit: Record, overrides: Record
) -> dict[str, object]:
    """Attach one source-bound trigger and reprioritize research only when due."""
    triggers = _mapping(overrides.get("review_triggers"), "review triggers")
    trigger = _mapping(triggers.get("zero_entry"), "zero-entry review trigger")
    _validate_decision_source(trigger, overrides)
    clock = build_cadence_review_clock(audit, trigger)
    output = dict(report)
    output["cadence_review_clock"] = clock
    output = _attach_route_clocks(output, audit, triggers, overrides)
    route_due = _first_due_route(output.get("route_cadence_review_clocks"))
    if route_due is not None:
        route, route_clock = route_due
        return _prioritize_route_review(output, route, route_clock)
    if clock["review_required"] is not True:
        return output
    assessment = dict(_mapping(report.get("assessment"), "report assessment"))
    assessment["recommendation"] = "run_predeclared_cadence_deviation_investigation"
    output["assessment"] = assessment
    output["highest_value_next_investigation"] = {
        "route": "portfolio",
        "experiment": clock["action"],
        "why_now": "complete_zero_entry_review_threshold_reached",
        "automatic_live_change": False,
    }
    return output


def _attach_route_clocks(
    report: dict[str, object], audit: Record, triggers: Record, overrides: Record
) -> dict[str, object]:
    raw_routes = triggers.get("route_zero_signal")
    if raw_routes is None:
        return report
    route_triggers = _mapping(raw_routes, "route zero-signal triggers")
    for raw_trigger in route_triggers.values():
        trigger = _mapping(raw_trigger, "route zero-signal trigger")
        _validate_decision_source(trigger, overrides)
    output = dict(report)
    output["route_cadence_review_clocks"] = build_route_cadence_review_clocks(
        audit, route_triggers
    )
    return output


def _first_due_route(value: object) -> tuple[str, Record] | None:
    if value is None:
        return None
    clocks = _mapping(value, "route cadence review clocks")
    for route, raw_clock in clocks.items():
        clock = _mapping(raw_clock, f"route cadence clock {route}")
        if clock.get("review_required") is True:
            return _text(route, "cadence route"), clock
    return None


def _prioritize_route_review(
    report: dict[str, object], route: str, clock: Record
) -> dict[str, object]:
    assessment = dict(_mapping(report.get("assessment"), "report assessment"))
    assessment["recommendation"] = "run_exact_route_cadence_investigation"
    output = dict(report)
    output["assessment"] = assessment
    output["highest_value_next_investigation"] = {
        "route": route,
        "experiment": _text(clock.get("action"), "route cadence action"),
        "why_now": "exact_route_zero_signal_threshold_reached",
        "automatic_live_change": False,
    }
    return output


def build_cadence_review_clock(audit: Record, trigger: Record) -> dict[str, object]:
    """Evaluate a predeclared zero-entry review threshold without live authority."""
    _validate_contract(_mapping(trigger.get("contract"), "review clock contract"))
    threshold = _positive_int(trigger.get("threshold_seconds"), "threshold seconds")
    run = _mapping(audit.get("run"), "audit run")
    elapsed = _elapsed_seconds(run)
    closed, opened = _lifecycle_counts(audit)
    coverage_complete = _coverage_complete(audit)
    status = _status(elapsed, threshold, closed + opened, coverage_complete)
    return {
        "status": status,
        "review_required": status == "review_due",
        "action": _text(trigger.get("action"), "review action"),
        "decision_source": _text(trigger.get("decision_source"), "decision source"),
        "elapsed_seconds": elapsed,
        "threshold_seconds": threshold,
        "remaining_seconds": max(threshold - elapsed, 0.0),
        "closed_lifecycles": closed,
        "open_lifecycles": opened,
        "coverage_complete": coverage_complete,
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
    }


def build_route_cadence_review_clocks(
    audit: Record, triggers: Record
) -> dict[str, dict[str, object]]:
    """Evaluate frozen zero-signal thresholds for each exact live route."""
    run = _mapping(audit.get("run"), "audit run")
    elapsed = _elapsed_seconds(run)
    complete = _coverage_complete(audit)
    scorecards = _route_scorecards(audit)
    clocks: dict[str, dict[str, object]] = {}
    ordered = sorted(triggers.items(), key=_route_trigger_order)
    for route, raw_trigger in ordered:
        route_id = _text(route, "cadence route")
        trigger = _mapping(raw_trigger, f"cadence trigger {route_id}")
        _validate_contract(_mapping(trigger.get("contract"), "review clock contract"))
        threshold = _positive_int(trigger.get("threshold_seconds"), "threshold seconds")
        priority = _positive_int(trigger.get("priority"), "route cadence priority")
        scorecard = _mapping(scorecards.get(route_id), f"scorecard {route_id}")
        eligible = _nonnegative_int(
            scorecard.get("eligible_signals"), "eligible signals"
        )
        status = _route_status(elapsed, threshold, eligible, complete)
        clocks[route_id] = _route_clock(
            trigger, status, elapsed, threshold, priority, eligible, complete
        )
    return clocks


def _route_clock(
    trigger: Record,
    status: str,
    elapsed: float,
    threshold: int,
    priority: int,
    eligible: int,
    complete: bool,
) -> dict[str, object]:
    return {
        "status": status,
        "review_required": status == "review_due",
        "action": _text(trigger.get("action"), "review action"),
        "decision_source": _text(trigger.get("decision_source"), "decision source"),
        "priority": priority,
        "elapsed_seconds": elapsed,
        "threshold_seconds": threshold,
        "remaining_seconds": max(threshold - elapsed, 0.0),
        "eligible_signals": eligible,
        "coverage_complete": complete,
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
    }


def _route_scorecards(audit: Record) -> Record:
    scorecard = _mapping(audit.get("strategy_scorecard"), "strategy scorecard")
    return _mapping(scorecard.get("by_provider_symbol"), "provider scorecards")


def _route_trigger_order(item: tuple[object, object]) -> tuple[int, str]:
    route, raw_trigger = item
    trigger = _mapping(raw_trigger, "route cadence trigger")
    priority = _positive_int(trigger.get("priority"), "route cadence priority")
    return priority, _text(route, "cadence route")


def _route_status(elapsed: float, threshold: int, eligible: int, complete: bool) -> str:
    if eligible:
        return "signal_observed"
    if not complete:
        return "coverage_incomplete"
    return "review_due" if elapsed >= threshold else "monitoring"


def _status(elapsed: float, threshold: int, lifecycles: int, complete: bool) -> str:
    if lifecycles:
        return "entry_observed"
    if not complete:
        return "coverage_incomplete"
    return "review_due" if elapsed >= threshold else "monitoring"


def _lifecycle_counts(audit: Record) -> tuple[int, int]:
    execution = _mapping(audit.get("execution"), "audit execution")
    closed = _nonnegative_int(execution.get("closed_trades"), "closed trades")
    assets = _mapping(execution.get("by_asset"), "execution assets")
    opened = sum(
        _nonnegative_int(
            _mapping(row, f"execution asset {symbol}").get("open_lifecycles"),
            f"open lifecycles {symbol}",
        )
        for symbol, row in assets.items()
    )
    return closed, opened


def _coverage_complete(audit: Record) -> bool:
    coverage = _mapping(audit.get("coverage"), "audit coverage")
    complete = coverage.get("complete")
    if not isinstance(complete, bool):
        raise ValueError("audit coverage complete must be boolean")
    gaps = coverage.get("technical_gaps")
    if not isinstance(gaps, list) or not all(isinstance(item, str) for item in gaps):
        raise ValueError("audit technical gaps must be a text array")
    return complete and not gaps


def _elapsed_seconds(run: Record) -> float:
    start = _timestamp(run.get("first_observed_at_utc"), "run start")
    end = _timestamp(run.get("last_observed_at_utc"), "run end")
    elapsed = (end - start).total_seconds()
    if elapsed < 0:
        raise ValueError("cadence review window cannot move backward")
    return elapsed


def _validate_contract(contract: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("cadence review trigger contract is invalid")


def _validate_decision_source(trigger: Record, overrides: Record) -> None:
    source = _text(trigger.get("decision_source"), "decision source")
    evidence = overrides.get("review_trigger_evidence", overrides.get("evidence"))
    if not isinstance(evidence, list):
        raise ValueError("research evidence must be an array")
    paths = {
        _text(_mapping(row, "research evidence row").get("path"), "evidence path")
        for row in evidence
    }
    if source not in paths:
        raise ValueError("cadence review decision source is not frozen evidence")


def _timestamp(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include timezone")
    return parsed.astimezone(UTC)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
