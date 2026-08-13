"""JSON-safe persistence contract for the SOL range-onset shadow state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Mapping, TypeVar, cast

from hypervector.research.range_onset_event_models import EventExitReason, EventSignal
from hypervector.research.sol_range_onset_shadow_models import (
    ShadowStatus,
    SharedCapitalSnapshot,
    SolShadowConfig,
    SolShadowPosition,
    SolShadowTrade,
)

_RESTORE_TYPE = TypeVar("_RESTORE_TYPE")
_EXIT_REASONS = {
    "liquidation",
    "stop",
    "opposite_signal",
    "signal",
    "max_hold",
    "end_of_data",
}


@dataclass(frozen=True)
class RestoredSolShadowState:
    """Validated state values used to reconstruct one engine."""

    status: ShadowStatus
    delta_usd: float
    capital: SharedCapitalSnapshot | None
    position: SolShadowPosition | None
    pending_entry: EventSignal | None
    pending_exit_reason: EventExitReason | None
    pending_exit_time_ms: int | None
    pending_reversal: EventSignal | None
    last_funding_hour_ms: int | None
    completed_trades: tuple[SolShadowTrade, ...]


def export_sol_shadow_state(
    *,
    config: SolShadowConfig,
    state: RestoredSolShadowState,
) -> dict[str, object]:
    """Return a JSON-safe complete lifecycle snapshot."""
    return {
        "schema_version": 1,
        "config_fingerprint": config.fingerprint,
        "status": state.status,
        "sol_realized_delta_usd": state.delta_usd,
        "capital": _asdict_optional(state.capital),
        "position": _asdict_optional(state.position),
        "pending_entry": _asdict_optional(state.pending_entry),
        "pending_exit_reason": state.pending_exit_reason,
        "pending_exit_time_ms": state.pending_exit_time_ms,
        "pending_reversal": _asdict_optional(state.pending_reversal),
        "last_funding_hour_ms": state.last_funding_hour_ms,
        "completed_trades": [asdict(trade) for trade in state.completed_trades],
    }


def restore_sol_shadow_state(
    config: SolShadowConfig,
    payload: Mapping[str, object],
) -> RestoredSolShadowState:
    """Validate and parse one complete lifecycle snapshot."""
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported SOL shadow state schema")
    if payload.get("config_fingerprint") != config.fingerprint:
        raise ValueError("SOL shadow config fingerprint changed across restart")
    status = payload.get("status")
    if status not in {"active", "evidence_failed"}:
        raise ValueError("invalid SOL shadow status")
    trades = payload.get("completed_trades")
    if not isinstance(trades, list):
        raise ValueError("completed_trades must be a list")
    return RestoredSolShadowState(
        cast(ShadowStatus, status),
        _number(payload, "sol_realized_delta_usd"),
        _restore_optional(SharedCapitalSnapshot, payload.get("capital")),
        _restore_optional(SolShadowPosition, payload.get("position")),
        _restore_optional(EventSignal, payload.get("pending_entry")),
        _optional_exit_reason(payload.get("pending_exit_reason")),
        _optional_integer(payload.get("pending_exit_time_ms"), "pending_exit_time_ms"),
        _restore_optional(EventSignal, payload.get("pending_reversal")),
        _optional_integer(payload.get("last_funding_hour_ms"), "last_funding_hour_ms"),
        tuple(_restore_required(SolShadowTrade, row) for row in trades),
    )


def _asdict_optional(value: object | None) -> dict[str, object] | None:
    if value is None:
        return None
    return cast(dict[str, object], asdict(value))  # type: ignore[arg-type]


def _restore_optional(
    model: type[_RESTORE_TYPE],
    value: object,
) -> _RESTORE_TYPE | None:
    if value is None:
        return None
    return _restore_required(model, value)


def _restore_required(
    model: type[_RESTORE_TYPE],
    value: object,
) -> _RESTORE_TYPE:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("SOL shadow state object must be a string-keyed mapping")
    return model(**cast(dict[str, object], value))


def _optional_exit_reason(value: object) -> EventExitReason | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in _EXIT_REASONS:
        raise ValueError("invalid pending_exit_reason")
    return cast(EventExitReason, value)


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number


def _optional_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer or null")
    return value
