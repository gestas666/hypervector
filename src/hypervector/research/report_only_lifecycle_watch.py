"""Shared durable publication for authority-none lifecycle evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import sys
import time

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.checkpoint_storage import write_atomic_json

Report = dict[str, object]
Refresh = Callable[[], object]
Sleep = Callable[[float], None]
TransientReason = Callable[[Exception], str | None]
TransientReporter = Callable[[str, Exception], None]


def validate_watch_snapshot(
    snapshot_path: Path, status: Mapping[str, object]
) -> dict[str, object]:
    """Verify immutable lifecycle bytes against their content-derived state ID."""
    expected_state_id = status.get("watch_state_id")
    if not isinstance(expected_state_id, str) or _state_id(status) != expected_state_id:
        raise ValueError("lifecycle watcher status and snapshot state differ")
    if not snapshot_path.is_file():
        raise FileNotFoundError(
            f"lifecycle watcher snapshot is missing: {snapshot_path}"
        )
    raw = snapshot_path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("lifecycle watcher snapshot must be an object")
    if payload.get("watch_state_id") != expected_state_id:
        raise ValueError("lifecycle watcher snapshot state differs")
    if _state_id(payload) != expected_state_id:
        raise ValueError("lifecycle watcher snapshot state differs")
    return {
        "path": str(snapshot_path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
        "watch_state_id": expected_state_id,
    }


def publish_watch_status(
    report: Report,
    *,
    status_path: Path,
    snapshot_dir: Path,
    run_id: str,
) -> Report:
    """Publish one atomic status and any newly resolved immutable snapshot."""
    _require_report_only(report)
    state_id = _state_id(report)
    snapshot = _snapshot_state(report, snapshot_dir, run_id, state_id)
    status = {
        **report,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "watch_state": report.get("state"),
        "watch_state_id": state_id,
        "snapshot": snapshot,
    }
    write_atomic_json(status_path, status)
    return status


def run_watch_loop(
    refresh: Refresh,
    *,
    interval_seconds: float,
    max_cycles: int,
    sleep_fn: Sleep = time.sleep,
    transient_exceptions: tuple[type[Exception], ...] = (),
    transient_reason: TransientReason | None = None,
    transient_reporter: TransientReporter | None = None,
    transient_retry_seconds: Mapping[str, float] | None = None,
) -> int:
    """Refresh until interrupted or the requested bounded cycles complete."""
    _validate_runtime(interval_seconds, max_cycles)
    retry_delays = dict(transient_retry_seconds or {})
    _validate_retry_delays(retry_delays)
    cycles = 0
    while True:
        delay = interval_seconds
        try:
            refresh()
        except transient_exceptions as exc:
            reason = transient_reason(exc) if transient_reason else None
            if reason is None:
                raise
            delay = retry_delays.get(reason, interval_seconds)
            if transient_reporter:
                transient_reporter(reason, exc)
        else:
            cycles += 1
            if max_cycles and cycles >= max_cycles:
                return 0
        sleep_fn(delay)


def report_transient_watch_failure(reason: str, exc: Exception) -> None:
    """Emit one structured degraded cycle without replacing valid evidence."""
    event = {
        "event_type": "report_only_watch_cycle_degraded",
        "reason": reason,
        "exception_type": type(exc).__name__,
    }
    print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)


def _require_report_only(report: Mapping[str, object]) -> None:
    contract = report.get("contract")
    valid = (
        isinstance(contract, Mapping)
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("portfolio_pnl_claimed") is False
        and contract.get("actual_orders_or_fills_claimed") is False
    )
    if not valid:
        raise ValueError("lifecycle watcher report-only contract is invalid")


def _state_id(report: Mapping[str, object]) -> str:
    selected = {
        field: report.get(field)
        for field in (
            "state",
            "contract",
            "identity",
            "summary",
            "latest_attempts",
            "latest_executions",
            "timer_evidence",
        )
    }
    raw = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    return sha256(raw).hexdigest()


def _snapshot_state(
    report: Report,
    snapshot_dir: Path,
    run_id: str,
    state_id: str,
) -> str | None:
    resolved = _resolved_count(report)
    if resolved == 0:
        return None
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{run_id}_{resolved:04d}_{state_id[:12]}.json"
    payload = {**report, "watch_state_id": state_id}
    if path.exists():
        validate_watch_snapshot(path, payload)
    else:
        write_immutable_json(path, payload)
    return str(path)


def _resolved_count(report: Mapping[str, object]) -> int:
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("lifecycle watcher summary must be a mapping")
    value = summary.get("resolved")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("lifecycle watcher resolved count must be nonnegative")
    return value


def _validate_runtime(interval_seconds: float, max_cycles: int) -> None:
    if not isfinite(interval_seconds) or interval_seconds <= 0.0:
        raise ValueError("lifecycle watcher interval must be finite and positive")
    if isinstance(max_cycles, bool) or not isinstance(max_cycles, int):
        raise ValueError("lifecycle watcher max cycles must be nonnegative")
    if max_cycles < 0:
        raise ValueError("lifecycle watcher max cycles must be nonnegative")


def _validate_retry_delays(delays: Mapping[str, float]) -> None:
    for reason, delay in delays.items():
        valid_reason = isinstance(reason, str) and bool(reason.strip())
        valid_delay = (
            not isinstance(delay, bool)
            and isinstance(delay, (int, float))
            and isfinite(delay)
            and delay > 0.0
        )
        if not valid_reason or not valid_delay:
            raise ValueError(
                "lifecycle watcher retry delays must be finite and positive"
            )
