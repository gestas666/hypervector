"""Read-only health probes with explicit unavailable-data reporting."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from hypervector_supervision.cohort_supervisor_models import (
    BACKEND_MARKER,
    DegradedStreak,
    HealthReport,
    HealthThresholds,
    SupervisorPaths,
)

# The decisions ledger is gigabytes and grows about 175 KB a minute, so 2 MiB
# covers roughly ten minutes of ordinary polls and hours of degraded-only ones.
LEDGER_TAIL_BYTES = 2 * 1024 * 1024
# The backend writes every degraded row of one cycle within milliseconds, and
# cycles start at least one poll interval (15 s) apart.
_SAME_POLL_GAP_SECONDS = 5.0
_EVENT_TYPE = re.compile(rb'"event_type"\s*:\s*"([^"\\]*)"')
_STREAK_EVENTS = frozenset(
    {b"heartbeat", b"cohort_snapshot", b"runtime_stopped", b"runtime_fault"}
)
_DETAIL_LIMIT = 160


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
    if result.returncode != 0:
        return False
    try:
        command = shlex.split(result.stdout)
    except ValueError:
        return False
    return _backend_command(command)


def _backend_command(command: list[str]) -> bool:
    """Match the actual Python entry point rather than incidental argv text."""
    if not command:
        return False
    for index, argument in enumerate(command[1:], start=1):
        if argument == "-m":
            return command[index + 1 : index + 2] == [
                "hypervector.operations.multi_asset_bidirectional_live"
            ]
        if argument == "-c":
            return False
        if argument.startswith("-"):
            continue
        return Path(argument).name == BACKEND_MARKER
    return False


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
        if not _is_hip3_symbol(fill.get("symbol")):
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


def _ledger_tail(path: Path, limit: int) -> tuple[list[bytes], bool]:
    """Return the complete lines in the last ``limit`` bytes, oldest first.

    The second value reports whether the window reached the start of the file.
    Only the tail is read: this runs every health cycle against a live ledger.
    """
    try:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            start = max(0, size - limit)
            handle.seek(start)
            data = handle.read(size - start)
    except OSError:
        return [], False
    lines = data.split(b"\n")
    if start > 0:
        lines = lines[1:]  # the first line is cut by the window
    return [line for line in lines if line.strip()], start == 0


def _row(line: bytes) -> dict[str, object] | None:
    try:
        value = json.loads(line)
    except (ValueError, UnicodeError):
        return None  # includes a row the backend is still appending
    return value if isinstance(value, dict) else None


def _stamp(row: dict[str, object]) -> float | None:
    value = row.get("observed_at_utc")
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return stamp.timestamp() if stamp.tzinfo is not None else None


def _payload(row: dict[str, object]) -> dict[str, object]:
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def _newest_run_id(lines: list[bytes]) -> object:
    for line in reversed(lines):
        row = _row(line)
        if row is not None:
            return row.get("run_id")
    return None


def _open_position_count(row: dict[str, object]) -> int | None:
    value = _payload(row).get("open_position_count")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def backend_degraded_streak(
    path: Path, *, now: float, freshness_seconds: float
) -> DegradedStreak | None:
    """Return the current run's trailing degraded polls, or None when polling is clean.

    A streak ends at a running heartbeat, at the start of the current run, or at
    a terminal runtime row. A streak whose newest row is older than
    ``freshness_seconds`` belongs to a backend that has stopped writing, which the
    heartbeat probe reports; it is not reported as degraded polling.
    """
    lines, whole_file = _ledger_tail(path, LEDGER_TAIL_BYTES)
    run_id = _newest_run_id(lines)
    degraded: list[tuple[float, dict[str, object]]] = []  # newest first
    open_positions: int | None = None
    snapshot_seen = closed = False
    for line in reversed(lines):
        match = _EVENT_TYPE.search(line)
        if match is None or match.group(1) not in _STREAK_EVENTS:
            continue
        row = _row(line)
        if row is None:
            continue
        if row.get("run_id") != run_id:
            closed = True
            break
        event = row.get("event_type")
        if event == "cohort_snapshot":
            if not snapshot_seen:
                snapshot_seen, open_positions = True, _open_position_count(row)
        elif not closed:
            stamp = _stamp(row)
            if (
                event == "heartbeat"
                and stamp is not None
                and (_payload(row).get("status") == "degraded")
            ):
                degraded.append((stamp, row))
            else:
                # A running heartbeat or a terminal runtime row ends the streak.
                closed = True
        if closed and (snapshot_seen or not degraded):
            break
    if not degraded or now - degraded[0][0] > freshness_seconds:
        return None
    stamps = sorted(stamp for stamp, _row_ in degraded)
    polls = 1 + sum(
        later - earlier > _SAME_POLL_GAP_SECONDS
        for earlier, later in zip(stamps, stamps[1:])
    )
    latest = _payload(degraded[0][1])
    source, reason = latest.get("source"), latest.get("reason")
    return DegradedStreak(
        polls=polls,
        started_at_utc=datetime.fromtimestamp(stamps[0], UTC).isoformat(),
        duration_seconds=max(0.0, now - stamps[0]),
        complete=closed or whole_file,
        source=source if isinstance(source, str) else None,
        reason=reason if isinstance(reason, str) else None,
        open_position_count=open_positions,
    )


def _degraded_problem(
    streak: DegradedStreak | None, limits: HealthThresholds
) -> str | None:
    """Return the alert detail when the streak crosses either operator bound."""
    if streak is None:
        return None
    exposed = streak.open_position_count != 0  # unknown counts as possibly open
    if not (
        streak.duration_seconds >= limits.degraded_seconds
        or (exposed and streak.polls >= limits.degraded_polls_with_positions)
    ):
        return None
    bound = "" if streak.complete else ">="
    positions = (
        "unknown"
        if streak.open_position_count is None
        else str(streak.open_position_count)
    )
    detail = (
        f"{bound}{streak.polls} polls, degraded {bound}"
        f"{streak.duration_seconds / 60.0:.1f} min, {positions} open positions, "
        f"last {streak.source or 'unknown'}: {streak.reason or 'unknown'}"
    )
    return detail[:_DETAIL_LIMIT]


def protection_warnings(
    checkpoint: dict[str, object] | None,
) -> tuple[tuple[dict[str, object], ...], bool]:
    """Read the backend's top-level ``protection_warnings`` checkpoint list.

    An absent, null or empty list is no warning. The second value reports
    content that is present but unreadable, which must not read as healthy.
    """
    value = checkpoint.get("protection_warnings") if checkpoint is not None else None
    if value is None:
        return (), False
    if not isinstance(value, list):
        return (), True
    valid = tuple(
        entry
        for entry in value
        if isinstance(entry, dict)
        and isinstance(entry.get("symbol"), str)
        and isinstance(entry.get("reason"), str)
    )
    return valid, len(valid) != len(value)


def _protection_detail(
    warnings: tuple[dict[str, object], ...], unreadable: bool
) -> str | None:
    parts = [
        f"{entry['symbol']} {entry.get('strategy_id')} "
        f"entry_oid={entry.get('entry_oid')}: {entry['reason']}"
        for entry in warnings
    ]
    if unreadable:
        parts.append("unreadable protection_warnings entry")
    return "; ".join(parts)[:_DETAIL_LIMIT] if parts else None


def _free_disk_problem(free_disk: float | None, limits: HealthThresholds) -> str | None:
    """Name the disk problem; the launch floor supersedes the early warning."""
    if free_disk is None:
        return "free_disk_unavailable"
    if free_disk < limits.minimum_free_disk_gib:
        return "free_disk_low"
    if free_disk < limits.free_disk_warning_gib:
        return "free_disk_warning"
    return None


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


def _is_hip3_symbol(value: object) -> bool:
    """A builder-deployed (HIP-3) market is named ``dex:ASSET``; core perps are not."""
    return isinstance(value, str) and ":" in value


def _active_hip3_symbols(checkpoint: dict[str, object] | None) -> set[str] | None:
    """Return the HIP-3 symbols in the live execution scope, or None if unknown."""
    audit = checkpoint.get("audit") if checkpoint is not None else None
    run = audit.get("run") if isinstance(audit, dict) else None
    scopes = run.get("executable_provider_symbols") if isinstance(run, dict) else None
    if not isinstance(scopes, list) or any(
        not isinstance(s, str) or "|" not in s for s in scopes
    ):
        return None
    return {
        symbol
        for scope in scopes
        if _is_hip3_symbol(symbol := scope.split("|", 1)[1])
    }


def _active_fee_problems(
    active: set[str] | None,
    markets: list[dict[str, object]] | None,
) -> list[str]:
    if active is None:
        return ["checkpoint_execution_scope_unavailable"]
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
    checkpoint: dict[str, object] | None,
) -> tuple[float | None, float | None, dict[str, str], float | None, list[str]]:
    roster = read_object(paths.roster)
    checkpoint_age = _probe_age(paths.checkpoint, checkpoint, "generated_at_utc", now)
    roster_age = _probe_age(paths.roster, roster, "observed_at_utc", now)
    markets, fills = _roster_markets(roster), _fill_rows(checkpoint)
    active = _active_hip3_symbols(checkpoint)
    problems = _active_fee_problems(active, markets)
    # The HIP-3 roster is only evidence for HIP-3 execution; a cohort whose
    # live scope has no HIP-3 market needs no roster observer.
    roster_required = active is None or bool(active)
    if markets is None and roster_required:
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
    for age, limit, label, required in (
        (checkpoint_age, limits.checkpoint_seconds, "checkpoint_stale", True),
        (roster_age, limits.roster_seconds, "roster_observer_stale", roster_required),
    ):
        if required and (age is None or age > limit):
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
    checkpoint = read_object(paths.checkpoint)
    checkpoint_age, roster_age, regime, fee, problems = _data_probes(
        paths, thresholds, now, checkpoint
    )
    details: dict[str, str] = {}
    free_disk = free_disk_gib(paths.ledger)
    disk_problem = _free_disk_problem(free_disk, thresholds)
    if disk_problem is not None:
        problems.append(disk_problem)
        if free_disk is not None:
            details[disk_problem] = f"{free_disk:.1f} GiB free"
    streak = backend_degraded_streak(
        paths.ledger, now=now, freshness_seconds=thresholds.degraded_freshness_seconds
    )
    degraded_detail = _degraded_problem(streak, thresholds)
    if degraded_detail is not None:
        problems.append("backend_polls_degraded")
        details["backend_polls_degraded"] = degraded_detail
    warnings, unreadable = protection_warnings(checkpoint)
    protection_detail = _protection_detail(warnings, unreadable)
    if protection_detail is not None:
        problems.append("protection_warning")
        details["protection_warning"] = protection_detail
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
        backend_degraded=streak,
        protection_warnings=warnings,
        problem_details=details,
    )
