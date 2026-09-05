"""Hash-bound open-lifecycle evidence for external research candidates."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

Record = Mapping[str, object]


def load_external_partial_lifecycle(
    catalog_path: Path,
    record: Record,
    *,
    symbol: str,
    provider_id: str,
    profile_id: str,
    observed_at: datetime,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Load immutable censored evidence without projecting a PnL result."""
    value = record.get("partial_lifecycle_source")
    if value is None:
        return None, None
    source = _mapping(value, "partial lifecycle source")
    path = _resolve(catalog_path, source.get("path"))
    raw = path.read_bytes()
    _require_exact_source(source, path, raw)
    payload = _mapping(json.loads(raw), "partial lifecycle payload")
    _require_contract(payload, symbol, provider_id, profile_id)
    timestamp, age_seconds = _observation_age(payload, observed_at)
    nominal = _scenario(payload, "nominal")
    stress = _scenario(payload, "stress")
    if nominal != stress:
        raise ValueError("partial lifecycle scenarios do not reconcile")
    event = _censor_event(nominal[2])
    return _status(payload, timestamp, age_seconds, nominal, event), _evidence(
        path, raw
    )


def _require_exact_source(source: Record, path: Path, raw: bytes) -> None:
    expected_hash = _text(source.get("sha256"), "partial lifecycle sha256")
    expected_bytes = _integer(source.get("bytes"), "partial lifecycle bytes")
    if expected_hash != sha256(raw).hexdigest() or expected_bytes != len(raw):
        raise ValueError(f"partial lifecycle evidence mismatch: {path}")


def _require_contract(
    payload: Record, symbol: str, provider_id: str, profile_id: str
) -> None:
    expected = {
        "schema_version": "hip3_shadow_lifecycle_replay_v2",
        "symbol": symbol,
        "provider_id": provider_id,
        "profile_id": profile_id,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise ValueError(f"partial lifecycle contract is invalid: {symbol}")
    technical = _mapping(payload.get("technical_assessment"), "technical assessment")
    required = {
        "all_lifecycle_paths_resolved": False,
        "entry_identity_reproduced": True,
        "live_promotion_supported": False,
    }
    if any(technical.get(field) != value for field, value in required.items()):
        raise ValueError(f"partial lifecycle technical state is invalid: {symbol}")


def _observation_age(payload: Record, observed_at: datetime) -> tuple[datetime, float]:
    if observed_at.tzinfo is None:
        raise ValueError("partial lifecycle observation time requires a timezone")
    observed_ms = _integer(payload.get("observed_at_ms"), "partial observed at")
    timestamp = datetime.fromtimestamp(observed_ms / 1_000.0, tz=UTC)
    age_seconds = (observed_at - timestamp).total_seconds()
    if age_seconds < 0.0:
        raise ValueError("partial lifecycle evidence is from the future")
    return timestamp, age_seconds


def _scenario(payload: Record, name: str) -> tuple[int, int, Record]:
    scenario = _mapping(payload.get(name), f"{name} partial lifecycle")
    completed = _integer(scenario.get("completed_lifecycles"), "completed lifecycles")
    censored = _integer(scenario.get("censored_lifecycles"), "censored lifecycles")
    if completed != 0 or censored != 1:
        raise ValueError("partial lifecycle must contain one censored open lifecycle")
    required_zero = ("wins", "losses", "net_pnl_usd")
    if any(_number(scenario.get(field), field) != 0.0 for field in required_zero):
        raise ValueError("partial lifecycle must not claim completed economics")
    required_null = (
        "mean_net_return_bps",
        "profit_factor",
        "net_without_largest_winner_usd",
    )
    if any(scenario.get(field) is not None for field in required_null):
        raise ValueError("partial lifecycle must not claim derived economics")
    events = scenario.get("censored")
    if not isinstance(events, list) or len(events) != censored:
        raise ValueError("partial lifecycle censor rows do not reconcile")
    return completed, censored, _mapping(events[0], "censored lifecycle")


def _censor_event(event: Record) -> dict[str, object]:
    decision_time_ms = _integer(event.get("decision_time_ms"), "decision time")
    entry_time_ms = _integer(event.get("entry_time_ms"), "entry time")
    if decision_time_ms == 0 or entry_time_ms < decision_time_ms:
        raise ValueError("partial lifecycle event times are invalid")
    if event.get("route_state_resolved_time_ms") is not None:
        raise ValueError("partial lifecycle unexpectedly has a resolved route state")
    side = _text(event.get("side"), "partial lifecycle side")
    reason = _text(event.get("reason"), "partial lifecycle censor reason")
    if side not in {"long", "short"} or reason != "exit_event_censored":
        raise ValueError("partial lifecycle censor identity is invalid")
    return {
        "side": side,
        "decision_time_ms": decision_time_ms,
        "entry_time_ms": entry_time_ms,
        "censor_reason": reason,
    }


def _status(
    payload: Record,
    timestamp: datetime,
    age_seconds: float,
    scenario: tuple[int, int, Record],
    event: dict[str, object],
) -> dict[str, object]:
    completed, censored, _ = scenario
    return {
        "evidence_state": "open_censored_lifecycle",
        "observed_at_utc": timestamp.isoformat(),
        "age_seconds": age_seconds,
        "provider_id": payload["provider_id"],
        "profile_id": payload["profile_id"],
        **event,
        "nominal_completed": completed,
        "nominal_censored": censored,
        "stress_completed": completed,
        "stress_censored": censored,
        "all_lifecycle_paths_resolved": False,
        "pnl_claimed": False,
        "live_change_supported": False,
    }


def _resolve(catalog_path: Path, value: object) -> Path:
    text = _text(value, "partial lifecycle path")
    path = Path(text)
    return path if path.is_absolute() else (catalog_path.parent / path).resolve()


def _evidence(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"external {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"external {label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"external {label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"external {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"external {label} must be finite")
    return number
