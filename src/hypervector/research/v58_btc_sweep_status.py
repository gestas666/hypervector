"""Fail-closed normalization of the exact V58 BTC sweep watcher status."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from hypervector.research.report_only_lifecycle_watch import validate_watch_snapshot

Record = Mapping[str, object]

_MODE = "v58_btc_sweep_exact_mark_depth_lifecycle_v1"
_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_STRATEGY = "liquidity_sweep_long_1h_stop60_target60_v2"


@dataclass(frozen=True)
class BtcSweepLifecycleStatus:
    """Normalized BTC sweep status and the exact source-file evidence."""

    state: str
    pending: int
    resolved: int
    technical_complete: bool
    source_age_seconds: float
    evidence: dict[str, object]


def load_v58_btc_sweep_lifecycle_status(
    path: Path,
    *,
    observer_run_id: str,
    observer_profile_fingerprint: str,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> BtcSweepLifecycleStatus:
    """Load one fresh status bound to the exact V58 observer and route."""
    _require_aware(observed_at)
    _require_positive(maximum_age_seconds, "maximum BTC lifecycle age")
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "BTC lifecycle status")
    _require_contract(payload, observer_run_id, observer_profile_fingerprint)
    summary = _mapping(payload.get("summary"), "BTC lifecycle summary")
    pending, resolved, incomplete = _require_summary(payload, summary)
    evidence: dict[str, object] = {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    snapshot = _snapshot(payload, resolved)
    if snapshot is not None:
        evidence["resolved_snapshot"] = snapshot
    return BtcSweepLifecycleStatus(
        state=_text(payload.get("watch_state"), "BTC watch state"),
        pending=pending,
        resolved=resolved,
        technical_complete=incomplete == 0,
        source_age_seconds=_source_age(
            payload.get("observed_at_utc"), observed_at, maximum_age_seconds
        ),
        evidence=evidence,
    )


def _require_contract(payload: Record, run_id: str, profile: str) -> None:
    top = {"schema_version": 1, "mode": _MODE}
    if any(payload.get(field) != value for field, value in top.items()):
        raise ValueError("BTC lifecycle source contract is invalid")
    contract = _mapping(payload.get("contract"), "BTC lifecycle contract")
    authority = {
        "report_only": True,
        "execution_authority": "none",
        "portfolio_pnl_claimed": False,
        "actual_orders_or_fills_claimed": False,
        "source_strategy_id": _STRATEGY,
        "symbol": "BTC",
        "source_run_id": run_id,
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": profile,
        "sides": ["long"],
    }
    if any(contract.get(field) != value for field, value in authority.items()):
        raise ValueError("BTC lifecycle authority or identity is invalid")
    frozen = {
        "notional_usd": 5_000.0,
        "stop_bps": 60.0,
        "target_bps": 60.0,
        "maximum_hold_minutes": 1_440,
        "maximum_entry_delay_ms": 30_000,
    }
    if any(contract.get(field) != value for field, value in frozen.items()):
        raise ValueError("BTC lifecycle frozen exit contract is invalid")
    _require_identity(payload, run_id, profile)


def _require_identity(payload: Record, run_id: str, profile: str) -> None:
    identity = _mapping(payload.get("identity"), "BTC lifecycle identity")
    expected = {
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": profile,
        "source_run_id": run_id,
    }
    if any(identity.get(field) != value for field, value in expected.items()):
        raise ValueError("BTC lifecycle observer identity is invalid")
    _nonnegative_integer(identity.get("prospective_start_ms"), "BTC prospective start")


def _require_summary(payload: Record, summary: Record) -> tuple[int, int, int]:
    pending = _nonnegative_integer(summary.get("pending"), "BTC pending")
    resolved = _nonnegative_integer(summary.get("resolved"), "BTC resolved")
    incomplete = _nonnegative_integer(
        summary.get("technical_incomplete"), "BTC incomplete"
    )
    selected = _nonnegative_integer(
        summary.get("selected_non_overlapping"), "BTC selected"
    )
    _nonnegative_integer(summary.get("overlapping_excluded"), "BTC overlapping")
    attempts = _sequence(payload.get("latest_attempts"), "BTC attempts")
    outcomes = _sequence(payload.get("latest_executions"), "BTC executions")
    if selected != pending + resolved + incomplete:
        raise ValueError("BTC lifecycle summary does not reconcile")
    if len(attempts) != selected or len(outcomes) != resolved:
        raise ValueError("BTC lifecycle summary does not reconcile to rows")
    if payload.get("state") != payload.get("watch_state"):
        raise ValueError("BTC lifecycle state does not reconcile")
    return pending, resolved, incomplete


def _snapshot(payload: Record, resolved: int) -> dict[str, object] | None:
    value = payload.get("snapshot")
    if resolved:
        path = Path(_text(value, "BTC resolved lifecycle snapshot"))
        return validate_watch_snapshot(path, payload)
    if value is not None:
        raise ValueError("BTC unresolved lifecycle has a snapshot")
    return None


def _source_age(value: object, observed_at: datetime, maximum_age: float) -> float:
    timestamp = datetime.fromisoformat(
        _text(value, "BTC lifecycle observation time").replace("Z", "+00:00")
    )
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("BTC lifecycle observation time must be timezone-aware")
    age = (observed_at.astimezone(UTC) - timestamp.astimezone(UTC)).total_seconds()
    if age < 0.0:
        raise ValueError("BTC lifecycle status is from the future")
    if age > maximum_age:
        raise ValueError("BTC lifecycle status is stale")
    return age


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("BTC lifecycle consolidation time must be timezone-aware")


def _require_positive(value: float, label: str) -> None:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
