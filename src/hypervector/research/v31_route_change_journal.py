"""Compact hash-chained material-change journal for v31 route evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import fcntl
from hashlib import sha256
import json
from pathlib import Path
from typing import TextIO

Record = Mapping[str, object]

_CONTRACT: dict[str, object] = {
    "report_only": True,
    "execution_authority": "none",
    "runtime_strategy_changed": False,
    "automatic_transition": False,
    "automatic_retuning": False,
}


@dataclass(frozen=True)
class RouteChangeJournalSpec:
    """Bind a material-change chain to one route snapshot generation."""

    label: str
    snapshot_schema: str
    event_schema: str


V31_CHANGE_JOURNAL_SPEC = RouteChangeJournalSpec(
    label="v31",
    snapshot_schema="v31_route_forward_snapshot_v1",
    event_schema="v31_route_material_change_v1",
)


def append_v31_material_change(path: Path, snapshot: Record) -> bool:
    """Append one state only when material v31 evidence changed."""
    return append_route_material_change(path, snapshot, V31_CHANGE_JOURNAL_SPEC)


def append_route_material_change(
    path: Path, snapshot: Record, spec: RouteChangeJournalSpec
) -> bool:
    """Append one hash-chained state for an exact versioned tracker."""
    material = _material_state(snapshot, spec)
    material_hash = _digest(material)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        prior = _validated_events(stream, spec)
        if prior and prior[-1]["material_state_sha256"] == material_hash:
            return False
        event = _event(snapshot, material, material_hash, prior, spec)
        stream.seek(0, 2)
        stream.write(_canonical_json(event) + "\n")
        stream.flush()
        return True


def _material_state(
    snapshot: Record, spec: RouteChangeJournalSpec
) -> dict[str, object]:
    _validate_snapshot_contract(snapshot, spec)
    routes = _mapping_sequence(snapshot.get("routes"), "snapshot routes")
    live = _mapping(snapshot.get("live_state"), "snapshot live state")
    assessment = _mapping(snapshot.get("assessment"), "snapshot assessment")
    return {
        "phase": _text(snapshot.get("phase"), "snapshot phase"),
        "tracking_state": _text(
            snapshot.get("tracking_state"), "snapshot tracking state"
        ),
        "source_run": _identity(
            _mapping(snapshot.get("source_run"), "snapshot source run"),
            "source run",
        ),
        "candidate": _identity(
            _mapping(snapshot.get("candidate"), "snapshot candidate"),
            "candidate",
            require_run_id=False,
        ),
        "assessment": _assessment(assessment),
        "health": _health(live),
        "performance": _execution_performance(
            _mapping(live.get("execution"), "live execution"), "live execution"
        ),
        "routes": sorted(
            (_route(row) for row in routes),
            key=lambda row: str(row["route"]),
        ),
    }


def _validate_snapshot_contract(snapshot: Record, spec: RouteChangeJournalSpec) -> None:
    if snapshot.get("schema_version") != spec.snapshot_schema:
        raise ValueError(f"{spec.label} snapshot schema is invalid")
    contract = _mapping(snapshot.get("contract"), "snapshot contract")
    if contract.get("report_only") is not True:
        raise ValueError(f"{spec.label} snapshot must be report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError(f"{spec.label} snapshot execution authority must be none")
    if contract.get("runtime_strategy_changed") is not False:
        raise ValueError(
            f"{spec.label} snapshot cannot claim a runtime strategy change"
        )


def _identity(
    value: Record,
    label: str,
    *,
    require_run_id: bool = True,
) -> dict[str, object]:
    result: dict[str, object] = {
        "profile_id": _text(value.get("profile_id"), f"{label} profile id"),
        "profile_fingerprint": _digest_text(
            value.get("profile_fingerprint"), f"{label} profile fingerprint"
        ),
    }
    if require_run_id:
        result["run_id"] = _text(value.get("run_id"), f"{label} run id")
    return result


def _assessment(value: Record) -> dict[str, object]:
    return {
        "automatic_transition_authorized": _boolean(
            value.get("automatic_transition_authorized"),
            "assessment automatic transition",
        ),
        "candidate_active": _boolean(
            value.get("candidate_active"), "assessment candidate active"
        ),
        "confidence": _text(value.get("confidence"), "assessment confidence"),
        "current_open_positions": _nonnegative_int(
            value.get("current_open_positions"), "assessment open positions"
        ),
        "recommendation": _text(
            value.get("recommendation"), "assessment recommendation"
        ),
    }


def _health(live: Record) -> dict[str, object]:
    positions = _mapping_sequence(live.get("open_positions"), "open positions")
    return {
        "faults": _nonnegative_int(live.get("faults"), "live faults"),
        "all_open_positions_protected": _boolean(
            live.get("all_open_positions_protected"), "live position protection"
        ),
        "open_positions": sorted(
            (_position(row) for row in positions),
            key=lambda row: str(row["symbol"]),
        ),
    }


def _position(value: Record) -> dict[str, object]:
    stop = value.get("stop_oid")
    if stop is not None:
        stop = _nonnegative_int(stop, "position stop oid")
    return {
        "symbol": _text(value.get("symbol"), "position symbol"),
        "position_size_signed": _finite_number(
            value.get("position_size_signed"), "position size"
        ),
        "protected_if_open": _boolean(
            value.get("protected_if_open"), "position protection"
        ),
        "stop_oid": stop,
    }


def _portfolio_observation(live: Record) -> dict[str, object]:
    portfolio = _mapping(live.get("portfolio"), "live portfolio")
    return {
        "final_equity_usd": _finite_number(
            portfolio.get("final_equity_usd"), "portfolio equity"
        ),
        "maximum_drawdown_pct": _finite_number(
            portfolio.get("maximum_drawdown_pct"), "portfolio drawdown"
        ),
        "maximum_margin_used_usd": _finite_number(
            portfolio.get("maximum_margin_used_usd"), "portfolio margin"
        ),
        "maximum_notional_usd": _finite_number(
            portfolio.get("maximum_notional_usd"), "portfolio notional"
        ),
    }


def _execution_performance(value: Record, label: str) -> dict[str, object]:
    profit_factor = value.get("profit_factor")
    if profit_factor is not None:
        profit_factor = _finite_number(profit_factor, f"{label} profit factor")
    return {
        "closed_trades": _nonnegative_int(
            value.get("closed_trades"), f"{label} closed trades"
        ),
        "wins": _nonnegative_int(value.get("wins"), f"{label} wins"),
        "losses": _nonnegative_int(value.get("losses"), f"{label} losses"),
        "net_pnl_usd": _finite_number(value.get("net_pnl_usd"), f"{label} net"),
        "profit_factor": profit_factor,
        "fees_usd": _finite_number(value.get("fees_usd"), f"{label} fees"),
        "funding_usd": _finite_number(value.get("funding_usd"), f"{label} funding"),
    }


def _route(value: Record) -> dict[str, object]:
    performance = value.get("execution_performance")
    if performance is not None:
        performance = _execution_performance(
            _mapping(performance, "route execution performance"),
            "route execution",
        )
    horizons = _mapping(value.get("eligible_signal_horizons"), "route signal horizons")
    return {
        "route": _text(value.get("route"), "route identity"),
        "group": _text(value.get("group"), "route group"),
        "current_authority": _text(
            value.get("current_authority"), "route current authority"
        ),
        "candidate_authority": _text(
            value.get("candidate_authority"), "route candidate authority"
        ),
        "eligible_signals": _nonnegative_int(
            value.get("eligible_signals"), "route eligible signals"
        ),
        "resolved_signal_horizons": _nonnegative_int(
            value.get("resolved_signal_horizons"), "route resolved horizons"
        ),
        "forward_assessment": _text(
            value.get("forward_assessment"), "route forward assessment"
        ),
        "eligible_signal_horizons": deepcopy(dict(horizons)),
        "execution_performance": performance,
    }


def _event(
    snapshot: Record,
    material: dict[str, object],
    material_hash: str,
    prior: Sequence[Record],
    spec: RouteChangeJournalSpec,
) -> dict[str, object]:
    live = _mapping(snapshot.get("live_state"), "snapshot live state")
    event: dict[str, object] = {
        "schema_version": spec.event_schema,
        "observed_at_utc": _text(
            snapshot.get("generated_at_utc"), "snapshot generation time"
        ),
        "source_checkpoint_generated_at_utc": _text(
            snapshot.get("source_checkpoint_generated_at_utc"),
            "source checkpoint generation time",
        ),
        "contract": dict(_CONTRACT),
        "previous_event_sha256": prior[-1]["event_sha256"] if prior else None,
        "material_state_sha256": material_hash,
        "portfolio_observation": _portfolio_observation(live),
        **material,
    }
    event["event_sha256"] = _digest(event)
    return event


def _validated_events(stream: TextIO, spec: RouteChangeJournalSpec) -> list[Record]:
    stream.seek(0)
    rows: list[Record] = []
    expected_previous: object = None
    for line_number, line in enumerate(stream, start=1):
        if not line.strip():
            raise ValueError(f"{spec.label} journal event {line_number} is blank")
        value = json.loads(line)
        row = _mapping(value, f"{spec.label} journal event {line_number}")
        _validate_event(row, expected_previous, line_number, spec)
        rows.append(row)
        expected_previous = row["event_sha256"]
    return rows


def _validate_event(
    row: Record,
    expected_previous: object,
    number: int,
    spec: RouteChangeJournalSpec,
) -> None:
    if row.get("schema_version") != spec.event_schema:
        raise ValueError(f"{spec.label} journal event {number} schema is invalid")
    if row.get("contract") != _CONTRACT:
        raise ValueError(f"{spec.label} journal event {number} contract is invalid")
    if row.get("previous_event_sha256") != expected_previous:
        raise ValueError(f"{spec.label} journal event {number} chain is invalid")
    event_hash = _digest_text(row.get("event_sha256"), "journal event hash")
    unsigned = dict(row)
    del unsigned["event_sha256"]
    if _digest(unsigned) != event_hash:
        raise ValueError(f"{spec.label} journal event {number} hash is invalid")
    material_hash = _digest_text(
        row.get("material_state_sha256"), "journal material hash"
    )
    material = _event_material(row)
    if _digest(material) != material_hash:
        raise ValueError(
            f"{spec.label} journal event {number} material hash is invalid"
        )


def _event_material(row: Record) -> dict[str, object]:
    keys = (
        "phase",
        "tracking_state",
        "source_run",
        "candidate",
        "assessment",
        "health",
        "performance",
        "routes",
    )
    return {key: deepcopy(row.get(key)) for key in keys}


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _mapping_sequence(value: object, label: str) -> list[Record]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return [_mapping(row, f"{label} row") for row in value]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _digest_text(value: object, label: str) -> str:
    result = _text(value, label)
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return result


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be finite")
    return result


def _canonical_json(value: Record) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value: Record) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()
