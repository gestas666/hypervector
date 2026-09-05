"""Canonical V58 context for the exact live BRENTOIL lifecycle watcher."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

Record = Mapping[str, object]

_ROUTE = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL"


@dataclass(frozen=True)
class BrentoilContinuousContext:
    """Authenticated current state for one exact live BRENTOIL lifecycle."""

    state: str
    pending: int
    resolved: int
    source_age_seconds: float
    payload: dict[str, object]
    evidence: dict[str, object]


def load_v58_brentoil_continuous_context(
    path: Path,
    *,
    observed_at: datetime,
    maximum_age_seconds: float,
    profile_id: str,
    profile_fingerprint: str,
    run_id: str,
) -> BrentoilContinuousContext:
    """Load one fresh open or immutable resolved authority-none status."""
    _require_aware(observed_at)
    _require_positive(maximum_age_seconds, "maximum age")
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "BRENTOIL watcher")
    _require_contract(payload)
    _require_identity(payload, profile_id, profile_fingerprint, run_id)
    state, pending, resolved = _state(payload)
    age = _source_age(payload.get("generated_at_utc"), observed_at)
    if state != "resolved" and age > maximum_age_seconds:
        raise ValueError("V58 BRENTOIL watcher status is stale")
    evidence = {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }
    return BrentoilContinuousContext(
        state, pending, resolved, age, dict(payload), evidence
    )


def attach_v58_brentoil_continuous_context(
    report: dict[str, object], context: BrentoilContinuousContext
) -> None:
    """Replace the canonical missing-capture row with exact watcher evidence."""
    _require_report_contract(_mapping(report.get("contract"), "report contract"))
    coverage = _mapping(report.get("lifecycle_capture_coverage"), "coverage")
    routes = _mutable_rows(coverage.get("routes"), "coverage routes")
    capture = _one_route(routes, "coverage")
    if capture.get("watcher_attached") is not False:
        raise ValueError("V58 BRENTOIL capture is already attached")
    prior_status = _text(capture.get("status"), "capture status")
    capture["watcher_attached"] = True
    capture["status"] = "exact_lifecycle_watcher_attached"
    coverage["watcher_count"] = (
        _nonnegative_int(coverage.get("watcher_count"), "watcher count") + 1
    )
    missing = _nonnegative_int(
        coverage.get("eligible_without_exact_capture"), "missing capture count"
    )
    if prior_status == "eligible_without_exact_lifecycle_capture":
        missing -= 1
    if missing < 0:
        raise ValueError("V58 BRENTOIL missing capture count is inconsistent")
    coverage["eligible_without_exact_capture"] = missing
    _attach_ledger(report, context)
    _attach_evidence(report, context)
    report["brentoil_live_lifecycle_context"] = _context_payload(context)


def _attach_ledger(
    report: dict[str, object], context: BrentoilContinuousContext
) -> None:
    rows = _mutable_rows(report.get("hypothesis_ledger"), "hypothesis ledger")
    row = _one_route(rows, "hypothesis ledger")
    row.update(
        {
            "status": "resolved_review_due" if context.resolved else "being_tested",
            "watch_state": context.state,
            "pending_lifecycles": context.pending,
            "resolved_lifecycles": context.resolved,
            "technical_complete": True,
            "source_age_seconds": context.source_age_seconds,
            "evidence_state": (
                "resolved_exact_live_lifecycle"
                if context.resolved
                else "open_exact_live_lifecycle"
            ),
            "automatic_live_change": False,
        }
    )


def _attach_evidence(
    report: dict[str, object], context: BrentoilContinuousContext
) -> None:
    evidence = _mapping(report.get("evidence"), "evidence")
    lifecycles = _mapping(evidence.get("lifecycles"), "lifecycle evidence")
    if _ROUTE in lifecycles:
        raise ValueError("V58 BRENTOIL lifecycle evidence is duplicated")
    lifecycles[_ROUTE] = dict(context.evidence)


def _context_payload(context: BrentoilContinuousContext) -> dict[str, object]:
    identity = dict(_mapping(context.payload.get("identity"), "watcher identity"))
    actual = dict(_mapping(context.payload.get("actual_live_lifecycle"), "lifecycle"))
    return {
        "state": context.state,
        "pending_lifecycles": context.pending,
        "resolved_lifecycles": context.resolved,
        "technical_complete": True,
        "source_age_seconds": context.source_age_seconds,
        "identity": identity,
        "actual_live_lifecycle": actual,
        "execution_authority": "none",
        "automatic_live_change": False,
    }


def _require_contract(payload: Record) -> None:
    expected = {
        "schema_version": 1,
        "mode": "v58_brentoil_live_lifecycle_reconciliation_v1",
        "strategy_change_supported": False,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL watcher source contract differs")
    contract = _mapping(payload.get("contract"), "BRENTOIL contract")
    safe = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "portfolio_pnl_claimed": False,
        "actual_orders_or_fills_claimed": True,
    }
    if any(contract.get(key) != value for key, value in safe.items()):
        raise ValueError("V58 BRENTOIL watcher authority differs")


def _require_identity(
    payload: Record, profile_id: str, fingerprint: str, run_id: str
) -> None:
    identity = _mapping(payload.get("identity"), "BRENTOIL identity")
    expected = {
        "profile_id": profile_id,
        "profile_fingerprint": fingerprint,
        "run_id": run_id,
        "route": _ROUTE,
        "symbol": "xyz:BRENTOIL",
        "side": "long",
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL watcher identity differs")
    lifecycle = _text(identity.get("lifecycle_id"), "lifecycle id")
    if not lifecycle.startswith("xyz:BRENTOIL:"):
        raise ValueError("V58 BRENTOIL lifecycle identity differs")


def _state(payload: Record) -> tuple[str, int, int]:
    state = _text(payload.get("state"), "watcher state")
    if state not in {"open_protected", "resolved"}:
        raise ValueError("V58 BRENTOIL watcher state differs")
    summary = _mapping(payload.get("summary"), "watcher summary")
    open_count = _nonnegative_int(summary.get("open"), "open count")
    resolved = _nonnegative_int(summary.get("resolved"), "resolved count")
    expected = (1, 0) if state == "open_protected" else (0, 1)
    if (open_count, resolved) != expected:
        raise ValueError("V58 BRENTOIL watcher summary differs")
    actual = _mapping(payload.get("actual_live_lifecycle"), "actual lifecycle")
    expected_exit = state == "resolved"
    if (
        actual.get("actual_entry_fill_claimed") is not True
        or actual.get("actual_exit_fill_claimed") is not expected_exit
    ):
        raise ValueError("V58 BRENTOIL actual lifecycle claims differ")
    return state, open_count, resolved


def _one_route(rows: Sequence[dict[str, object]], label: str) -> dict[str, object]:
    matches = [row for row in rows if row.get("route") == _ROUTE]
    if len(matches) != 1:
        raise ValueError(f"V58 BRENTOIL {label} route is missing or duplicated")
    return matches[0]


def _mutable_rows(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"V58 BRENTOIL {label} must be a list")
    output: list[dict[str, object]] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError(f"V58 BRENTOIL {label} rows must be mutable objects")
        output.append(row)
    return output


def _require_report_contract(contract: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 continuous report authority differs")


def _source_age(value: object, observed_at: datetime) -> float:
    timestamp = datetime.fromisoformat(_text(value, "generated time"))
    if timestamp.tzinfo is None:
        raise ValueError("V58 BRENTOIL watcher timestamp lacks timezone")
    age = (observed_at.astimezone(UTC) - timestamp.astimezone(UTC)).total_seconds()
    if age < 0.0:
        raise ValueError("V58 BRENTOIL watcher status is from the future")
    return age


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"V58 BRENTOIL {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 BRENTOIL {label} must be non-empty text")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"V58 BRENTOIL {label} must be nonnegative")
    return value


def _require_positive(value: object, label: str) -> None:
    valid = (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(float(value))
        and float(value) > 0.0
    )
    if not valid:
        raise ValueError(f"V58 BRENTOIL {label} must be positive")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("V58 BRENTOIL observed time must be timezone-aware")
