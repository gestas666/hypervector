"""Read-only health probes with explicit unavailable-data reporting."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from cohort_supervisor_models import (
    BACKEND_MARKER,
    HealthReport,
    HealthThresholds,
    SupervisorPaths,
)


def read_object(path: Path) -> dict[str, object] | None:
    """Read an object or return unavailable; callers must expose that condition."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


_FUTURE_MTIME_TOLERANCE_SECONDS = 5.0


def file_age_seconds(path: Path, now: float) -> float | None:
    """Return write age, preserving missing files as unavailable.

    A mtime in the future is reported as unavailable rather than clamped to zero:
    clamping would turn a backward wall-clock step into "just written" on the only
    liveness probe an owned child has, which is exactly what ``observation_age``
    already refuses to do.
    """
    try:
        age = now - path.stat().st_mtime
    except OSError:
        return None
    if age < -_FUTURE_MTIME_TOLERANCE_SECONDS:
        return None
    return max(0.0, age)


def mtime_in_future(path: Path, now: float) -> bool:
    """Report a clock regression distinctly from an absent or stale file."""
    try:
        return now - path.stat().st_mtime < -_FUTURE_MTIME_TOLERANCE_SECONDS
    except OSError:
        return False


def free_disk_gib(path: Path) -> float | None:
    """Return free space on the volume that holds the live ledger.

    Measured against the ledger rather than the repository root so a data volume
    mounted separately from the checkout is the one that gets reported.
    """
    probe = path if path.exists() else path.parent
    try:
        return shutil.disk_usage(probe).free / 1024**3
    except OSError:
        return None


def read_lock_pid(path: Path) -> int | None:
    """Read a positive PID without accepting malformed lock contents."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return int(text) if text.isdigit() and int(text) > 0 else None


def process_is_backend(pid: int) -> bool:
    """Confirm a live process has the exact backend entrypoint argument."""
    try:
        os.kill(pid, 0)
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and any(
        Path(part).name == BACKEND_MARKER for part in result.stdout.split()
    )


def observation_age(
    payload: dict[str, object] | None, key: str, now: float
) -> float | None:
    """Validate an aware observation time; future or missing times are unavailable."""
    value = payload.get(key) if payload is not None else None
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            return None
        age = now - stamp.timestamp()
    except (ValueError, OverflowError):
        return None
    return age if math.isfinite(age) and age >= 0 else None


def _roster_markets(
    payload: dict[str, object] | None,
) -> list[dict[str, object]] | None:
    if payload is None or payload.get("status") != "available":
        return None
    if payload.get("lifecycle") != "running":
        return None
    markets = payload.get("markets")
    if not isinstance(markets, list) or not markets:
        return None
    result: list[dict[str, object]] = []
    for row in markets:
        if not isinstance(row, dict) or not isinstance(row.get("symbol"), str):
            return None
        if not isinstance(row.get("venue"), dict):
            return None
        result.append(row)
    symbols = [row["symbol"] for row in result]
    if len(set(symbols)) != len(symbols) or payload.get("active_symbols") != symbols:
        return None
    return result


def _fee_regime(markets: list[dict[str, object]]) -> dict[str, str]:
    findings: dict[str, str] = {}
    for market in markets:
        symbol, venue = market["symbol"], market["venue"]
        if not isinstance(symbol, str) or not isinstance(venue, dict):
            raise ValueError("validated roster lost its symbol/venue identity")
        if venue.get("effective_fee_status") == "unresolved_growth_mode":
            continue
        if venue.get("growth_mode") is not True:
            findings[symbol] = f"growth_mode={venue.get('growth_mode')!r}"
        elif venue.get("deployer_fee_scale") != 1.0:
            findings[symbol] = f"deployer_fee_scale={venue.get('deployer_fee_scale')!r}"
    return findings


def hip3_fee_regime(path: Path) -> dict[str, str]:
    """Return fee changes; evaluate_health separately reports unavailable snapshots."""
    markets = _roster_markets(read_object(path))
    return _fee_regime(markets) if markets is not None else {}


def _fill_rows(payload: dict[str, object] | None) -> list[dict[str, object]] | None:
    audit = payload.get("audit") if payload is not None else None
    execution = audit.get("execution") if isinstance(audit, dict) else None
    fills = execution.get("fill_details") if isinstance(execution, dict) else None
    if not isinstance(fills, list) or any(not isinstance(row, dict) for row in fills):
        return None
    return fills


def _maximum_fee(
    fills: list[dict[str, object]], now: float, lookback: float
) -> float | None:
    earliest_ms = (now - lookback * 3600.0) * 1000.0
    rates: list[float] = []
    for fill in fills:
        if not str(fill.get("symbol", "")).startswith("xyz:"):
            continue
        values = [
            fill.get(key) for key in ("price", "size", "venue_timestamp_ms", "fee_usd")
        ]
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in values
        ):
            raise ValueError("HIP-3 fill fee evidence has missing/non-numeric fields")
        price, size, stamp, fee = (float(value) for value in values)
        if (
            not all(math.isfinite(value) for value in (price, size, stamp, fee))
            or price <= 0
            or size <= 0
        ):
            raise ValueError("HIP-3 fill fee evidence has invalid finite values")
        if earliest_ms <= stamp <= now * 1000.0:
            rates.append(fee / (price * size) * 10_000.0)
    return max(rates) if rates else None


def maximum_hip3_fill_fee_bps(
    path: Path, *, now: float, lookback_hours: float
) -> float | None:
    """Return recent fee maximum; invalid evidence is reported by evaluate_health."""
    rows = _fill_rows(read_object(path))
    return _maximum_fee(rows, now, lookback_hours) if rows is not None else None


def _probe_age(
    path: Path,
    payload: dict[str, object] | None,
    key: str,
    now: float,
) -> float | None:
    file_age = file_age_seconds(path, now)
    observed_age = observation_age(payload, key, now)
    if file_age is None or observed_age is None:
        return None
    return max(file_age, observed_age)


def _active_fee_problems(
    checkpoint: dict[str, object] | None,
    markets: list[dict[str, object]] | None,
) -> list[str]:
    audit = checkpoint.get("audit") if checkpoint is not None else None
    run = audit.get("run") if isinstance(audit, dict) else None
    scopes = run.get("executable_provider_symbols") if isinstance(run, dict) else None
    if not isinstance(scopes, list) or any(
        not isinstance(s, str) or "|" not in s for s in scopes
    ):
        return ["checkpoint_execution_scope_unavailable"]
    active = {scope.split("|", 1)[1] for scope in scopes if "|xyz:" in scope}
    venues = {row["symbol"]: row["venue"] for row in markets or ()}
    if any(
        not isinstance(venues.get(symbol), dict)
        or venues[symbol].get("effective_fee_status") != "resolved"
        for symbol in active
    ):
        return ["hip3_active_fee_evidence_unavailable"]
    return []


def _data_probes(
    paths: SupervisorPaths,
    limits: HealthThresholds,
    now: float,
) -> tuple[float | None, float | None, dict[str, str], float | None, list[str]]:
    checkpoint, roster = read_object(paths.checkpoint), read_object(paths.roster)
    checkpoint_age = _probe_age(paths.checkpoint, checkpoint, "generated_at_utc", now)
    roster_age = _probe_age(paths.roster, roster, "observed_at_utc", now)
    markets, fills = _roster_markets(roster), _fill_rows(checkpoint)
    problems = _active_fee_problems(checkpoint, markets)
    if markets is None:
        problems.append("roster_observer_unavailable")
    if fills is None:
        problems.append("checkpoint_unavailable")
    regime = _fee_regime(markets) if markets is not None else {}
    fee = None
    try:
        fee = (
            _maximum_fee(fills, now, limits.fee_lookback_hours)
            if fills is not None
            else None
        )
    except ValueError:
        problems.append("hip3_fill_fee_unavailable")
    for age, limit, label in (
        (checkpoint_age, limits.checkpoint_seconds, "checkpoint_stale"),
        (roster_age, limits.roster_seconds, "roster_observer_stale"),
    ):
        if age is None or age > limit:
            problems.append(label)
    if regime:
        problems.append("hip3_fee_regime_changed")
    if fee is not None and fee > limits.hip3_fee_bps:
        problems.append("hip3_fill_fee_above_threshold")
    return checkpoint_age, roster_age, regime, fee, problems


def evaluate_health(
    paths: SupervisorPaths,
    thresholds: HealthThresholds,
    *,
    now: float,
    is_backend: Callable[[int], bool] = process_is_backend,
    heartbeat_required: bool = True,
) -> HealthReport:
    """Report failures explicitly without creating execution or mutation authority."""
    pid = read_lock_pid(paths.process_lock)
    alive = pid is not None and is_backend(pid)
    ledger_age = file_age_seconds(paths.ledger, now)
    checkpoint_age, roster_age, regime, fee, problems = _data_probes(
        paths, thresholds, now
    )
    free_disk = free_disk_gib(paths.ledger)
    if free_disk is None:
        problems.append("free_disk_unavailable")
    elif free_disk < thresholds.minimum_free_disk_gib:
        problems.append("free_disk_low")
    if mtime_in_future(paths.ledger, now):
        problems.append("ledger_mtime_in_future")
    if not alive:
        problems.append("backend_process_absent")
    if heartbeat_required and (
        ledger_age is None or ledger_age > thresholds.heartbeat_seconds
    ):
        problems.append("backend_heartbeat_stale")
    return HealthReport(
        checked_at_utc=datetime.fromtimestamp(now, UTC).isoformat(),
        backend_pid=pid,
        backend_alive=alive,
        ledger_age_seconds=ledger_age,
        checkpoint_age_seconds=checkpoint_age,
        roster_age_seconds=roster_age,
        stop_file_present=paths.stop_file.exists(),
        maximum_hip3_fill_fee_bps=fee,
        hip3_fee_regime=regime,
        free_disk_gib=free_disk,
        problems=tuple(problems),
    )
