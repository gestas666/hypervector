"""Exact-route, report-only lifecycle evidence for a live cohort run."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from hypervector.research.cohort_route_lifecycle_scope import (
    RouteLifecycleBoundary,
    decision_is_prospective as _decision_is_prospective,
    prospective_readiness as _prospective_readiness,
    validate_freshness as _validate_freshness,
)

from hypervector.research.cohort_route_lifecycle_values import (
    REPORT_CONTRACT as _CONTRACT,
    boolean_field as _boolean_field,
    count as _count,
    evidence_mapping as _evidence_mapping,
    integer_field as _integer_field,
    mapping as _mapping,
    nested_mapping as _nested_mapping,
    number_field as _number_field,
    records as _records,
    require_unique_lifecycles as _require_unique_lifecycles,
    side as _side,
    text as _text,
    text_field as _text_field,
    text_sequence as _text_sequence,
    timestamp as _timestamp,
    validate_report_contract as _validate_contract,
)

Record = Mapping[str, object]

_SIDES = frozenset(("long", "short"))


@dataclass(frozen=True)
class RouteLifecycleIdentity:
    """Frozen run, provider, signal, symbol, and side identity."""

    run_id: str
    profile_id: str
    profile_fingerprint: str
    provider_id: str
    signal_strategy_id: str
    symbol: str
    required_sides: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject incomplete or ambiguous route identities."""
        for field in (
            "run_id",
            "profile_id",
            "profile_fingerprint",
            "provider_id",
            "signal_strategy_id",
            "symbol",
        ):
            _text(getattr(self, field), field.replace("_", " "))
        if len(self.profile_fingerprint) != 64:
            raise ValueError("profile fingerprint must have 64 characters")
        if not self.required_sides or len(set(self.required_sides)) != len(
            self.required_sides
        ):
            raise ValueError("required sides must be non-empty and unique")
        if any(side not in _SIDES for side in self.required_sides):
            raise ValueError("required sides must contain only long or short")

    @property
    def route(self) -> str:
        """Return the canonical provider-symbol route identity."""
        return f"{self.provider_id}|{self.symbol}"


def build_route_lifecycle_status(
    checkpoint: Record,
    identity: RouteLifecycleIdentity,
    *,
    boundary: RouteLifecycleBoundary,
    observed_at: datetime,
    maximum_checkpoint_age_seconds: float = 180.0,
) -> dict[str, object]:
    """Build fail-closed prospective progress for one exact live route."""
    generated_at = _validate_checkpoint(
        checkpoint, identity, observed_at, maximum_checkpoint_age_seconds
    )
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    readiness = _route_readiness(audit, identity, boundary)
    closed = _closed_lifecycles(audit, identity, boundary.capture_start_ms)
    opened = _open_lifecycles(audit, identity, boundary.capture_start_ms)
    attributable = len(closed) + len(opened)
    eligible = _count(
        readiness.get("prospective_eligible"), "prospective eligible evaluations"
    )
    if attributable > eligible:
        raise ValueError("route lifecycle count exceeds eligible evaluations")
    resolved = [row for row in closed if row["fully_resolved"] is True]
    unresolved = [row for row in closed if row["fully_resolved"] is not True]
    progress = _side_progress(identity.required_sides, closed, opened)
    minimum_met = all(row["minimum_met"] is True for row in progress.values())
    unattributed = eligible - attributable
    return _report(
        identity,
        boundary,
        generated_at,
        readiness,
        closed,
        opened,
        resolved,
        unresolved,
        progress,
        minimum_met,
        unattributed,
    )


def _validate_checkpoint(
    checkpoint: Record,
    identity: RouteLifecycleIdentity,
    observed_at: datetime,
    maximum_age: float,
) -> datetime:
    _validate_contract(checkpoint.get("checkpoint_contract"), "checkpoint")
    _validate_runtime(checkpoint, identity)
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    _validate_contract(audit.get("experiment_contract"), "audit")
    _validate_run(_mapping(audit.get("run"), "audit run"), identity)
    generated_at = _timestamp(checkpoint.get("generated_at_utc"), "checkpoint time")
    _validate_freshness(generated_at, observed_at, maximum_age)
    return generated_at


def _validate_runtime(checkpoint: Record, identity: RouteLifecycleIdentity) -> None:
    lifecycle = _mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    if lifecycle.get("state") != "running_consistent":
        raise ValueError("route lifecycle tracker requires a consistent live runtime")
    if lifecycle.get("backend_process_health") != "healthy":
        raise ValueError("route lifecycle tracker requires a healthy backend")
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    if generation.get("matches_runtime") is not True:
        raise ValueError("route lifecycle tracker requires the current configuration")
    for field in ("current_profile_fingerprint", "runtime_profile_fingerprint"):
        if generation.get(field) != identity.profile_fingerprint:
            raise ValueError(f"configuration {field.replace('_', ' ')} mismatch")
    directions = _mapping(
        generation.get("current_provider_execution_directions"),
        "provider execution directions",
    )
    observed = _text_sequence(directions.get(identity.route), "route directions")
    if tuple(observed) != identity.required_sides:
        raise ValueError("route execution directions differ from frozen sides")


def _validate_run(run: Record, identity: RouteLifecycleIdentity) -> None:
    expected = {
        "run_id": identity.run_id,
        "profile_id": identity.profile_id,
        "profile_fingerprint": identity.profile_fingerprint,
    }
    for field, value in expected.items():
        if run.get(field) != value:
            raise ValueError(f"audit {field.replace('_', ' ')} mismatch")
    routes = _text_sequence(
        run.get("executable_provider_symbols"), "executable provider symbols"
    )
    if identity.route not in routes:
        raise ValueError("frozen route is not executable in the current run")
    symbol_routes = [route for route in routes if route.endswith(f"|{identity.symbol}")]
    wrapped_signal = identity.provider_id != identity.signal_strategy_id
    if wrapped_signal and symbol_routes != [identity.route]:
        raise ValueError("exact lifecycle attribution requires a unique provider")


def _route_readiness(
    audit: Record,
    identity: RouteLifecycleIdentity,
    boundary: RouteLifecycleBoundary,
) -> dict[str, int]:
    readiness = _mapping(audit.get("readiness"), "audit readiness")
    rows = _mapping(readiness.get("by_provider_symbol"), "route readiness")
    route = _mapping(rows.get(identity.route), "selected route readiness")
    return _prospective_readiness(route, boundary)


def _closed_lifecycles(
    audit: Record, identity: RouteLifecycleIdentity, capture_start_ms: int
) -> list[dict[str, object]]:
    section = _mapping(audit.get("trade_reflections"), "trade reflections")
    rows = _records(section.get("trades"), "closed trade reflections")
    selected = [
        row
        for row in rows
        if _closed_matches(row, identity)
        and _decision_is_prospective(row, capture_start_ms)
    ]
    projected = [_project_closed(row, identity) for row in selected]
    _require_unique_lifecycles(projected)
    return projected


def _open_lifecycles(
    audit: Record, identity: RouteLifecycleIdentity, capture_start_ms: int
) -> list[dict[str, object]]:
    section = _mapping(audit.get("open_trade_reflections"), "open reflections")
    rows = _records(section.get("trades"), "open trade reflections")
    selected = [
        row
        for row in rows
        if _open_matches(row, identity)
        and _decision_is_prospective(row, capture_start_ms)
    ]
    projected = [_project_open(row, identity) for row in selected]
    _require_unique_lifecycles(projected)
    return projected


def _closed_matches(row: Record, identity: RouteLifecycleIdentity) -> bool:
    return (
        row.get("source_run_id") == identity.run_id
        and row.get("symbol") == identity.symbol
        and row.get("entry_strategy_id") == identity.signal_strategy_id
    )


def _open_matches(row: Record, identity: RouteLifecycleIdentity) -> bool:
    return (
        row.get("source_run_id") == identity.run_id
        and row.get("symbol") == identity.symbol
        and row.get("strategy_id") == identity.signal_strategy_id
    )


def _project_closed(row: Record, identity: RouteLifecycleIdentity) -> dict[str, object]:
    _validate_lifecycle_identity(row, identity, closed=True)
    missing: list[str] = []
    entry = _evidence_mapping(row, "entry", missing)
    exit_fill = _evidence_mapping(row, "exit", missing)
    protection = _evidence_mapping(row, "protective_stop", missing)
    hold = _evidence_mapping(row, "completed_hold_capture", missing)
    entry_signal = _entry_signal(row, identity, missing)
    projected = {
        "lifecycle_id": _text(row.get("lifecycle_id"), "lifecycle id"),
        "side": _side(row.get("side")),
        "fully_resolved": False,
        "missing_evidence_fields": missing,
        "entry_signal": entry_signal,
        "entry": _fill(entry, "entry", missing),
        "protection": _protection(protection, missing),
        "exit": _fill(exit_fill, "exit", missing),
        "costs": _costs(row, entry, exit_fill, missing),
        "outcome": _outcome(row, hold, missing),
        "exit_attribution": _exit_attribution(row, missing),
    }
    if hold and hold.get("status") != "resolved":
        missing.append("completed_hold_capture.status=resolved")
    projected["fully_resolved"] = not missing
    return projected


def _project_open(row: Record, identity: RouteLifecycleIdentity) -> dict[str, object]:
    _validate_lifecycle_identity(row, identity, closed=False)
    missing: list[str] = []
    entry = _evidence_mapping(row, "entry", missing)
    protection = _evidence_mapping(row, "protective_stop", missing)
    entry_signal = _entry_signal(row, identity, missing)
    return {
        "lifecycle_id": _text(row.get("lifecycle_id"), "open lifecycle id"),
        "side": _side(row.get("side")),
        "fully_resolved": False,
        "missing_evidence_fields": missing,
        "entry_signal": entry_signal,
        "entry": _fill(entry, "entry", missing),
        "protection": _protection(protection, missing),
        "holding_time_ms": _number_field(row, "holding_time_ms", missing),
        "marked_economics": dict(
            _mapping(row.get("marked_economics"), "open marked economics")
        ),
        "exit_plan": dict(_mapping(row.get("exit_plan"), "open exit plan")),
    }


def _validate_lifecycle_identity(
    row: Record, identity: RouteLifecycleIdentity, *, closed: bool
) -> None:
    if row.get("source_run_id") != identity.run_id:
        raise ValueError("route lifecycle source run mismatch")
    fingerprint = row.get("source_profile_fingerprint")
    if closed and fingerprint != identity.profile_fingerprint:
        raise ValueError("route lifecycle source profile fingerprint mismatch")
    strategy_field = "entry_strategy_id" if closed else "strategy_id"
    if row.get(strategy_field) != identity.signal_strategy_id:
        raise ValueError("route lifecycle signal strategy mismatch")
    _side(row.get("side"))


def _entry_signal(
    row: Record, identity: RouteLifecycleIdentity, missing: list[str]
) -> dict[str, object]:
    context = _evidence_mapping(row, "entry_context", missing)
    signal = _nested_mapping(context, "signal_provider", "entry signal", missing)
    if not signal:
        return {}
    expected_side = _side(row.get("side"))
    expected = {
        "strategy_id": identity.signal_strategy_id,
        "eligible": True,
        "side": expected_side,
        "decision_action": f"enter_{expected_side}",
    }
    if any(signal.get(field) != value for field, value in expected.items()):
        raise ValueError("lifecycle entry signal attribution is inconsistent")
    return dict(signal)


def _fill(row: Record, label: str, missing: list[str]) -> dict[str, object]:
    if not row:
        return {}
    return {
        "price": _number_field(row, "price", missing, prefix=label),
        "size": _number_field(row, "size", missing, prefix=label),
        "venue_timestamp_ms": _integer_field(
            row, "venue_timestamp_ms", missing, prefix=label
        ),
    }


def _protection(row: Record, missing: list[str]) -> dict[str, object]:
    if not row:
        return {}
    return {
        "oid": _integer_field(row, "oid", missing, prefix="protective_stop"),
        "trigger_price": _number_field(
            row, "trigger_price", missing, prefix="protective_stop"
        ),
    }


def _costs(
    row: Record, entry: Record, exit_fill: Record, missing: list[str]
) -> dict[str, object]:
    return {
        "entry_slippage_bps": _number_field(
            entry, "slippage_bps", missing, prefix="entry"
        ),
        "exit_slippage_bps": _number_field(
            exit_fill, "slippage_bps", missing, prefix="exit"
        ),
        "fees_usd": _number_field(row, "fees_usd", missing),
        "funding_usd": _number_field(row, "funding_usd", missing),
    }


def _outcome(row: Record, hold: Record, missing: list[str]) -> dict[str, object]:
    fields = (
        "maximum_favorable_excursion_bps",
        "maximum_adverse_excursion_bps",
        "peak_giveback_bps",
        "realized_gross_return_bps",
        "realized_net_return_bps",
        "observed_cost_hurdle_bps",
        "gross_mfe_capture_ratio",
    )
    output = (
        {
            field: _number_field(hold, field, missing, prefix="completed_hold_capture")
            for field in fields
        }
        if hold
        else {field: None for field in fields}
    )
    output.update(
        {
            "net_pnl_usd": _number_field(row, "net_pnl_usd", missing),
            "net_return_on_margin_pct": _number_field(
                row, "net_return_on_margin_pct", missing
            ),
            "entry_margin_used_usd": _number_field(
                row, "entry_margin_used_usd", missing
            ),
            "holding_time_ms": _integer_field(row, "holding_time_ms", missing),
            "economic_outcome": hold.get("economic_outcome"),
        }
    )
    return output


def _exit_attribution(row: Record, missing: list[str]) -> dict[str, object]:
    return {
        "exit_reason": _text_field(row, "exit_reason", missing),
        "exit_controller_strategy_id": _text_field(
            row, "exit_controller_strategy_id", missing
        ),
        "cross_provider_exit": _boolean_field(row, "cross_provider_exit", missing),
        "exit_oid": _integer_field(row, "exit_oid", missing),
    }


def _side_progress(
    sides: Sequence[str],
    closed: Sequence[Record],
    opened: Sequence[Record],
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for side in sides:
        side_closed = [row for row in closed if row.get("side") == side]
        resolved = sum(row.get("fully_resolved") is True for row in side_closed)
        open_count = sum(row.get("side") == side for row in opened)
        output[side] = {
            "attributable_entries": len(side_closed) + open_count,
            "open_lifecycles": open_count,
            "closed_lifecycles": len(side_closed),
            "resolved_lifecycles": resolved,
            "minimum_met": resolved >= 1,
        }
    return output


def _report(
    identity: RouteLifecycleIdentity,
    boundary: RouteLifecycleBoundary,
    generated_at: datetime,
    readiness: Record,
    closed: list[dict[str, object]],
    opened: list[dict[str, object]],
    resolved: list[dict[str, object]],
    unresolved: list[dict[str, object]],
    progress: dict[str, dict[str, object]],
    minimum_met: bool,
    unattributed: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_exact_route_lifecycle_evidence",
        "observed_at_utc": generated_at.isoformat(),
        "state": _state(progress, opened, unresolved, unattributed, minimum_met),
        "contract": dict(_CONTRACT),
        "identity": _identity_payload(identity),
        "prospective_boundary": {
            "capture_start_ms": boundary.capture_start_ms,
            "baseline_evaluations": boundary.baseline_evaluations,
            "baseline_eligible": boundary.baseline_eligible,
        },
        "route_readiness": {
            "evaluations": readiness["count"],
            "eligible": readiness["eligible"],
            "prospective_evaluations": readiness["prospective_evaluations"],
            "prospective_eligible": readiness["prospective_eligible"],
            "unattributed_eligible_evaluations": unattributed,
        },
        "side_progress": progress,
        "open_lifecycles": opened,
        "closed_lifecycles": closed,
        "resolved_lifecycles": resolved,
        "unresolved_lifecycles": unresolved,
        "minimum_diagnostic_evidence_met": minimum_met,
        "live_change_supported": False,
    }


def _state(
    progress: Record,
    opened: Sequence[Record],
    unresolved: Sequence[Record],
    unattributed: int,
    minimum_met: bool,
) -> str:
    if unresolved or any(row.get("missing_evidence_fields") for row in opened):
        return "technical_evidence_pending"
    if unattributed:
        return "eligible_evidence_unattributed"
    if minimum_met:
        return "diagnostic_minimum_complete"
    if opened:
        return "tracking_open_lifecycle"
    pending = [
        side
        for side, row in progress.items()
        if _mapping(row, f"{side} progress").get("minimum_met") is not True
    ]
    if len(pending) == 1:
        return f"awaiting_{pending[0]}"
    return "awaiting_both_sides"


def _identity_payload(identity: RouteLifecycleIdentity) -> dict[str, object]:
    return {
        "run_id": identity.run_id,
        "profile_id": identity.profile_id,
        "profile_fingerprint": identity.profile_fingerprint,
        "provider_id": identity.provider_id,
        "signal_strategy_id": identity.signal_strategy_id,
        "symbol": identity.symbol,
        "route": identity.route,
        "required_sides": list(identity.required_sides),
    }
