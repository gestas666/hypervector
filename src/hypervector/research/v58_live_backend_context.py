"""Fresh armed-backend health for the report-only V58 research loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.v58_live_open_lifecycles import (
    extract_v58_live_open_lifecycles,
)
from hypervector.research.v58_live_closed_lifecycles import (
    extract_v58_live_closed_lifecycles,
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class LiveBackendContext:
    """Validated distinction between live execution and observer health."""

    profile_id: str
    profile_fingerprint: str
    run_id: str
    lifecycle_state: str
    backend_process_health: str
    heartbeat_status: str
    checkpoint_age_seconds: float
    backend_event_age_seconds: float
    last_event_type: str
    last_observed_at_utc: str
    runtime_fault_exception_type: str | None
    ledger_asset_states: dict[str, str]
    ledger_last_snapshot_flat_order_free: bool
    evidence: dict[str, object]
    execution_authority: str = "none"
    live_runtime: dict[str, object] = field(default_factory=dict)
    live_entry_submission_timing: dict[str, object] = field(default_factory=dict)
    open_lifecycles: dict[str, object] = field(default_factory=dict)
    closed_lifecycles: dict[str, object] = field(default_factory=dict)


def load_v58_live_backend_context(
    checkpoint_path: Path,
    *,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> LiveBackendContext:
    """Load a fresh report-only checkpoint without inferring venue positions."""
    observed = _aware_utc(observed_at, "observation time")
    maximum_age = _positive_number(maximum_age_seconds, "maximum age")
    reference = file_evidence(checkpoint_path)
    raw = checkpoint_path.read_bytes()
    if _raw_evidence(raw) != reference:
        raise ValueError("V58 live backend checkpoint changed while reading")
    payload = _mapping(json.loads(raw), "live backend checkpoint")
    _require_report_only(payload)
    generated = _timestamp(payload.get("generated_at_utc"), "checkpoint generated_at")
    checkpoint_age = _age_seconds(observed, generated, maximum_age)
    audit = _mapping(payload.get("audit"), "audit")
    run = _mapping(audit.get("run"), "run")
    lifecycle = _mapping(payload.get("lifecycle"), "lifecycle")
    health = _mapping(_mapping(payload["audit"], "audit").get("health"), "health")
    venue = _mapping(payload.get("venue_portfolio"), "venue portfolio")
    _require_venue_report_only(venue)
    context = _context(run, lifecycle, health, audit, observed, checkpoint_age)
    runtime = _live_runtime(audit)
    entry_timing = _live_entry_submission_timing(audit)
    open_lifecycles = extract_v58_live_open_lifecycles(
        audit,
        run_id=str(context[2]),
        symbols=tuple(context[11]),
    )
    closed_lifecycles = extract_v58_live_closed_lifecycles(
        audit,
        run_id=str(context[2]),
        profile_fingerprint=str(context[1]),
        routes=_string_list(run.get("executable_provider_symbols"), "run routes"),
    )
    if file_evidence(checkpoint_path) != reference:
        raise ValueError("V58 live backend checkpoint changed during evaluation")
    evidence = {"checkpoint": {"path": str(checkpoint_path.resolve()), **reference}}
    return LiveBackendContext(
        *context,
        evidence,
        live_runtime=runtime,
        live_entry_submission_timing=entry_timing,
        open_lifecycles=open_lifecycles,
        closed_lifecycles=closed_lifecycles,
    )


def live_backend_context_payload(context: LiveBackendContext) -> dict[str, object]:
    """Serialize backend state without claiming current venue reconciliation."""
    running = (
        context.lifecycle_state == "running_consistent"
        and context.backend_process_health == "healthy"
        and context.heartbeat_status == "running"
    )
    return {
        "measurement_scope": "active_live_checkpoint",
        "profile_id": context.profile_id,
        "profile_fingerprint": context.profile_fingerprint,
        "run_id": context.run_id,
        "lifecycle_state": context.lifecycle_state,
        "backend_process_health": context.backend_process_health,
        "heartbeat_status": context.heartbeat_status,
        "checkpoint_age_seconds": context.checkpoint_age_seconds,
        "backend_event_age_seconds": context.backend_event_age_seconds,
        "last_event_type": context.last_event_type,
        "last_observed_at_utc": context.last_observed_at_utc,
        "runtime_fault_exception_type": context.runtime_fault_exception_type,
        "ledger_asset_states": context.ledger_asset_states,
        "ledger_last_snapshot_flat_order_free": (
            context.ledger_last_snapshot_flat_order_free
        ),
        "live_runtime": context.live_runtime,
        "live_entry_submission_timing": context.live_entry_submission_timing,
        "open_lifecycles": context.open_lifecycles,
        "closed_lifecycles": context.closed_lifecycles,
        "live_execution_running": running,
        "operator_attention_required": not running,
        "current_venue_position_order_state_verified": False,
        "automatic_live_change": False,
        "execution_authority": context.execution_authority,
    }


def _live_runtime(audit: Record) -> dict[str, object]:
    runtime = _mapping(audit.get("runtime"), "live runtime")
    cycles = _positive_integer(runtime.get("poll_cycles"), "live poll cycles")
    intervals = _metric(runtime.get("poll_interval_seconds"), "live poll interval")
    if intervals["count"] != cycles - 1:
        raise ValueError("V58 live poll interval count is inconsistent")
    reasons = _count_map(runtime.get("stop_reasons"), "live stop reasons")
    return {
        "poll_cycles": cycles,
        "poll_interval_seconds": intervals,
        "stop_reasons": reasons,
    }


def _live_entry_submission_timing(audit: Record) -> dict[str, object]:
    routing = _mapping(audit.get("routing"), "live routing")
    timing = _mapping(routing.get("entry_age_diagnostics"), "live entry timing")
    eligible = _nonnegative_integer(timing.get("eligible_evaluations"), "eligible")
    actions = _nonnegative_integer(timing.get("enter_actions"), "enter actions")
    submitted = _nonnegative_integer(timing.get("submitted_entries"), "submitted")
    stale = _nonnegative_integer(timing.get("stale_entries_withheld"), "stale")
    observed = _boolean(timing.get("submission_timestamp_observed"), "observed")
    enforced = _boolean(
        timing.get("entry_submission_enforcement_observed"), "enforcement"
    )
    late = _boolean(timing.get("executed_late_entries_proven"), "late entries")
    headroom, route_submitted, route_late = _submission_routes(timing)
    if submitted != route_submitted or late != (route_late > 0):
        raise ValueError("V58 live submission aggregates are inconsistent")
    if observed != (submitted + stale > 0) or enforced != (
        observed and submitted == actions
    ):
        raise ValueError("V58 live submission enforcement is inconsistent")
    return _submission_timing_payload(
        eligible, actions, submitted, stale, observed, enforced, late, headroom
    )


def _submission_routes(timing: Record) -> tuple[int | None, int, int]:
    routes = _mapping(timing.get("by_provider_symbol"), "live timing routes")
    headrooms: list[int] = []
    submitted = 0
    late = 0
    for route, value in routes.items():
        _text(route, "live timing route")
        row = _mapping(value, f"live timing route {route}")
        count = _nonnegative_integer(row.get("submitted_entries"), "route submitted")
        submitted += count
        late += _nonnegative_integer(
            row.get("submitted_entries_over_limit"), "route late entries"
        )
        headroom = row.get("minimum_submission_headroom_ms")
        if count:
            headrooms.append(_integer(headroom, "submission headroom"))
        elif headroom is not None:
            raise ValueError("V58 unused live route has submission headroom")
    return (min(headrooms) if headrooms else None), submitted, late


def _submission_timing_payload(
    eligible: int,
    actions: int,
    submitted: int,
    stale: int,
    observed: bool,
    enforced: bool,
    late: bool,
    headroom: int | None,
) -> dict[str, object]:
    status = "contract_breach" if late else "not_yet_observed"
    if enforced and not late:
        status = "submission_contract_enforced"
    return {
        "status": status,
        "eligible_evaluations": eligible,
        "enter_actions": actions,
        "submitted_entries": submitted,
        "stale_entries_withheld": stale,
        "submission_timestamp_observed": observed,
        "entry_submission_enforcement_observed": enforced,
        "executed_late_entries_proven": late,
        "minimum_submission_headroom_ms": headroom,
    }


def _context(
    run: Record,
    lifecycle: Record,
    health: Record,
    audit: Record,
    observed: datetime,
    checkpoint_age: float,
) -> tuple[object, ...]:
    symbols = _string_list(run.get("symbols"), "run symbols")
    states, flat = _ledger_states(symbols, lifecycle, health, audit)
    state = _text(lifecycle.get("state"), "lifecycle state")
    process = _text(lifecycle.get("backend_process_health"), "process health")
    heartbeat = _text(lifecycle.get("cohort_heartbeat_status"), "heartbeat status")
    fault = _optional_text(lifecycle.get("runtime_fault_exception_type"))
    if state == "backend_runtime_fault" and (process != "faulted" or fault is None):
        raise ValueError("V58 backend runtime-fault identity is inconsistent")
    last_text = _text(lifecycle.get("cohort_last_observed_at_utc"), "last event time")
    event_age = _nonnegative_age(observed, _timestamp(last_text, "last event time"))
    return (
        _text(run.get("profile_id"), "profile id"),
        _sha256_text(run.get("profile_fingerprint"), "profile fingerprint"),
        _text(run.get("run_id"), "run id"),
        state,
        process,
        heartbeat,
        checkpoint_age,
        event_age,
        _text(lifecycle.get("cohort_last_event_type"), "last event type"),
        last_text,
        fault,
        states,
        flat,
    )


def _ledger_states(
    symbols: tuple[str, ...], lifecycle: Record, health: Record, audit: Record
) -> tuple[dict[str, str], bool]:
    lifecycle_states = _mapping(lifecycle.get("asset_states"), "asset states")
    assets = _mapping(health.get("assets"), "health assets")
    if set(lifecycle_states) != set(symbols) or set(assets) != set(symbols):
        raise ValueError("V58 live backend asset coverage is inconsistent")
    positions = _execution_position_sizes(audit, symbols)
    states: dict[str, str] = {}
    flat_order_free = True
    for symbol in symbols:
        row = _mapping(assets[symbol], f"{symbol} health")
        state = _text(row.get("final_state"), f"{symbol} state")
        if lifecycle_states[symbol] != state:
            raise ValueError(f"V58 {symbol} asset state is inconsistent")
        size = _health_position_size(symbol, state, row, positions)
        orders = _health_order_ids(symbol, state, row)
        states[symbol] = state
        flat_order_free &= state == "FLAT" and size == 0.0 and not orders
    return states, flat_order_free


def _execution_position_sizes(
    audit: Record, symbols: tuple[str, ...]
) -> dict[str, float]:
    execution = _mapping(audit.get("execution"), "execution")
    values = execution.get("open_positions")
    if not isinstance(values, list):
        raise ValueError("V58 execution open positions must be a list")
    positions: dict[str, float] = {}
    for value in values:
        row = _mapping(value, "execution open position")
        symbol = _text(row.get("symbol"), "execution open position symbol")
        size = _number(row.get("size_signed"), f"{symbol} execution position size")
        if symbol not in symbols or symbol in positions or size == 0.0:
            raise ValueError("V58 execution open-position coverage is invalid")
        positions[symbol] = size
    return positions


def _health_position_size(
    symbol: str, state: str, row: Record, positions: Mapping[str, float]
) -> float:
    reported = row.get("position_size_signed")
    if reported is not None:
        size = _number(reported, f"{symbol} position size")
        if positions.get(symbol, 0.0) != size:
            raise ValueError(f"V58 {symbol} health and execution positions disagree")
        return size
    if state == "FLAT" and symbol not in positions:
        return 0.0
    if state == "OPEN" and symbol in positions:
        return positions[symbol]
    raise ValueError(f"V58 {symbol} state has no exact execution position")


def _health_order_ids(symbol: str, state: str, row: Record) -> tuple[int, ...]:
    reported = row.get("open_order_ids")
    if reported is None:
        stop_oid = row.get("stop_oid")
        orders = () if stop_oid is None else (_positive_integer(stop_oid, "stop oid"),)
    elif isinstance(reported, list):
        orders = tuple(_positive_integer(value, "open order oid") for value in reported)
    else:
        raise ValueError(f"V58 {symbol} open orders are invalid")
    if len(orders) != len(set(orders)) or (state == "FLAT" and orders):
        raise ValueError(f"V58 {symbol} open orders are inconsistent")
    return orders


def _require_report_only(payload: Record) -> None:
    contract = _mapping(payload.get("checkpoint_contract"), "checkpoint contract")
    required = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
    }
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError("V58 live backend checkpoint lacks a report-only contract")


def _require_venue_report_only(venue: Record) -> None:
    contract = _mapping(venue.get("contract"), "venue portfolio contract")
    unavailable = (
        venue.get("status") == "unavailable"
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("execution_collateral_unchanged") is True
        and bool(_text(venue.get("technical_issue"), "venue portfolio issue"))
    )
    if unavailable:
        raise ValueError("V58 venue portfolio is temporarily unavailable")
    if (
        venue.get("status") != "observed"
        or contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("V58 venue portfolio is not report-only observed evidence")
    _timestamp(venue.get("observed_at_utc"), "venue portfolio observed_at")


def _age_seconds(observed: datetime, generated: datetime, maximum: float) -> float:
    age = _nonnegative_age(observed, generated)
    if age > maximum:
        raise ValueError("V58 live backend checkpoint is stale")
    return age


def _nonnegative_age(observed: datetime, source: datetime) -> float:
    age = (observed - source).total_seconds()
    if age < 0.0:
        raise ValueError("V58 live backend evidence is from the future")
    return age


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"V58 {label} must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"V58 {label} is invalid") from exc
    return _aware_utc(parsed, label)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be a mapping")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"V58 {label} must be a non-empty list")
    output = tuple(_text(item, label) for item in value)
    if len(output) != len(set(output)):
        raise ValueError(f"V58 {label} must be unique")
    return output


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 {label} must be non-empty text")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value, "optional text")


def _sha256_text(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"V58 {label} must be lowercase sha256")
    return text


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    output = float(value)
    if not isfinite(output):
        raise ValueError(f"V58 {label} must be finite")
    return output


def _positive_number(value: object, label: str) -> float:
    output = _number(value, label)
    if output <= 0.0:
        raise ValueError(f"V58 {label} must be positive")
    return output


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"V58 {label} must be an integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    output = _integer(value, label)
    if output < 0:
        raise ValueError(f"V58 {label} must be nonnegative")
    return output


def _positive_integer(value: object, label: str) -> int:
    output = _integer(value, label)
    if output <= 0:
        raise ValueError(f"V58 {label} must be positive")
    return output


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"V58 {label} must be boolean")
    return value


def _metric(value: object, label: str) -> dict[str, object]:
    metric = _mapping(value, label)
    count = _nonnegative_integer(metric.get("count"), f"{label} count")
    minimum = _positive_number(metric.get("minimum"), f"{label} minimum")
    median = _positive_number(metric.get("median"), f"{label} median")
    mean = _positive_number(metric.get("mean"), f"{label} mean")
    maximum = _positive_number(metric.get("maximum"), f"{label} maximum")
    if not minimum <= median <= maximum or not minimum <= mean <= maximum:
        raise ValueError(f"V58 {label} is inconsistent")
    return {
        "count": count,
        "minimum": minimum,
        "median": median,
        "mean": mean,
        "maximum": maximum,
    }


def _count_map(value: object, label: str) -> dict[str, int]:
    source = _mapping(value, label)
    result: dict[str, int] = {}
    for key, count in source.items():
        result[_text(key, f"{label} key")] = _positive_integer(count, label)
    return dict(sorted(result.items()))


def _raw_evidence(raw: bytes) -> dict[str, object]:
    return {"sha256": sha256(raw).hexdigest(), "bytes": len(raw)}
