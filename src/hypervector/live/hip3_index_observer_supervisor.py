"""Process supervision for the two report-only HIP-3 index observers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Protocol

from hypervector.live.hip3_fresh15_journal_provider import (
    require_fresh_index_observers,
)
from hypervector.live.hip3_provider_availability import (
    Hip3ObserverUnavailableError,
)
from hypervector.runtime_lock import cohort_checkpoint_writer_active

_MIXED_PUBLICATION_REASON = "observer_checkpoint_publication_incomplete"
_STALE_STATUS_REASON = "observer_status_stale"
_RECOVERABLE_HEALTH_REASONS = frozenset(
    {_STALE_STATUS_REASON, "observer_runtime_degraded_transient"}
)


class IndexObserverSupervisorError(RuntimeError):
    """The report-only index observer pair cannot be supervised safely."""


class ObserverProcess(Protocol):
    """Child process operations required by the supervisor."""

    returncode: int | None

    def poll(self) -> int | None:
        """Return the exit status or ``None`` while running."""

    def terminate(self) -> None:
        """Request graceful child shutdown."""

    def wait(self, timeout: float | None = None) -> int:
        """Wait for child shutdown and return its status."""

    def kill(self) -> None:
        """Force child shutdown after the grace period."""


@dataclass(frozen=True)
class IndexObserverRoute:
    """Files and command owned by one index observer child."""

    symbol: str
    command: tuple[str, ...]
    status: Path
    cursor: Path
    journal: Path
    log: Path


@dataclass(frozen=True)
class IndexObserverSupervisorConfig:
    """Polling and shutdown policy for the report-only pair."""

    status: Path
    poll_seconds: float = 1.0
    warmup_seconds: float = 45.0
    stop_timeout_seconds: float = 5.0
    maximum_status_silence_seconds: float = 20.0
    restart_budget_reset_seconds: float = 300.0
    maximum_restarts_per_route: int = 3

    def __post_init__(self) -> None:
        """Reject nonpositive durations or an unbounded restart policy."""
        durations = (
            self.poll_seconds,
            self.warmup_seconds,
            self.stop_timeout_seconds,
            self.maximum_status_silence_seconds,
            self.restart_budget_reset_seconds,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value <= 0.0
            for value in durations
        ):
            raise ValueError("index observer supervisor policy is invalid")
        if (
            isinstance(self.maximum_restarts_per_route, bool)
            or not isinstance(self.maximum_restarts_per_route, int)
            or self.maximum_restarts_per_route < 0
        ):
            raise ValueError("index observer supervisor policy is invalid")


@dataclass(frozen=True)
class _OwnedRoute:
    route: IndexObserverRoute
    process: ObserverProcess
    restart_count: int
    started_ms: int
    prior_status_ms: int
    prior_cursor_boundary: int | None
    prior_journal: bytes
    started_monotonic: float
    ready: bool = False


SpawnFn = Callable[[IndexObserverRoute], ObserverProcess]
HealthCheck = Callable[[datetime], None]


def supervise_index_observers(
    config: IndexObserverSupervisorConfig,
    routes: tuple[IndexObserverRoute, ...],
    *,
    spawn_fn: SpawnFn | None = None,
    owner_active_fn: Callable[[Path], bool] = cohort_checkpoint_writer_active,
    health_check: HealthCheck = require_fresh_index_observers,
    clock_ms_fn: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    """Restart a failed child without disrupting its healthy sibling."""
    launcher = _spawn_observer if spawn_fn is None else spawn_fn
    owned: tuple[_OwnedRoute, ...] = ()
    publication_incomplete_since: float | None = None
    try:
        _validate_routes(config.status, routes)
        _require_unowned_routes(routes, owner_active_fn)
        owned = tuple(
            _start_route(route, launcher, clock_ms_fn, monotonic_fn, 0)
            for route in routes
        )
        while not stop_requested():
            owned = _refresh_owned_routes(
                owned, config, launcher, clock_ms_fn, monotonic_fn
            )
            try:
                owned, publication_incomplete_since = _mark_ready(
                    owned,
                    config,
                    health_check,
                    clock_ms_fn,
                    monotonic_fn,
                    publication_incomplete_since,
                )
            except Hip3ObserverUnavailableError as exc:
                if exc.reason not in _RECOVERABLE_HEALTH_REASONS:
                    raise
                publication_incomplete_since = None
                health_issue = exc.reason
            else:
                health_issue = _publication_health_issue(publication_incomplete_since)
            _write_status(config, owned, clock_ms_fn(), health_issue=health_issue)
            sleep_fn(config.poll_seconds)
        _stop_children(owned, config.stop_timeout_seconds)
        _write_status(config, owned, clock_ms_fn(), status="stopped")
        return 0
    except (IndexObserverSupervisorError, ValueError, OSError) as exc:
        _write_fault_status(config, owned, str(exc), clock_ms_fn())
        raise
    finally:
        _stop_children(owned, config.stop_timeout_seconds)


def _publication_health_issue(incomplete_since: float | None) -> str | None:
    return _MIXED_PUBLICATION_REASON if incomplete_since is not None else None


def _refresh_owned_routes(
    owned: tuple[_OwnedRoute, ...],
    config: IndexObserverSupervisorConfig,
    launcher: SpawnFn,
    clock_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
) -> tuple[_OwnedRoute, ...]:
    current = tuple(
        _replace_exited(state, config, launcher, clock_ms_fn, monotonic_fn)
        for state in owned
    )
    current = tuple(
        _replace_stale(state, config, launcher, clock_ms_fn, monotonic_fn)
        for state in current
    )
    return tuple(
        _replace_unready_timeout(state, config, launcher, clock_ms_fn, monotonic_fn)
        for state in current
    )


def _replace_unready_timeout(
    state: _OwnedRoute,
    config: IndexObserverSupervisorConfig,
    spawn_fn: SpawnFn,
    clock_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
) -> _OwnedRoute:
    if state.ready:
        return state
    if monotonic_fn() - state.started_monotonic < config.warmup_seconds:
        return state
    _stop_process(state.process, config.stop_timeout_seconds)
    return _restart_route(
        state, config, spawn_fn, clock_ms_fn, monotonic_fn, "warmup timeout"
    )


def _require_unowned_routes(
    routes: tuple[IndexObserverRoute, ...], owner_active_fn: Callable[[Path], bool]
) -> None:
    for route in routes:
        if owner_active_fn(route.status):
            raise IndexObserverSupervisorError(
                f"index observer already owns {route.status}"
            )


def _start_route(
    route: IndexObserverRoute,
    spawn_fn: SpawnFn,
    clock_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
    restart_count: int,
) -> _OwnedRoute:
    status = _json_object(route.status)
    cursor = _json_object(route.cursor)
    prior_status = _optional_integer(status.get("observed_at_ms"))
    prior_journal = _read_bytes(route.journal)
    started_ms = clock_ms_fn()
    started_monotonic = monotonic_fn()
    process = spawn_fn(route)
    return _OwnedRoute(
        route,
        process,
        restart_count,
        started_ms,
        -1 if prior_status is None else prior_status,
        _optional_integer(cursor.get("decision_time_ms")),
        prior_journal,
        started_monotonic,
    )


def _replace_exited(
    state: _OwnedRoute,
    config: IndexObserverSupervisorConfig,
    spawn_fn: SpawnFn,
    clock_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
) -> _OwnedRoute:
    exit_code = state.process.poll()
    if exit_code is None:
        return state
    return _restart_route(
        state, config, spawn_fn, clock_ms_fn, monotonic_fn, f"exit {exit_code}"
    )


def _replace_stale(
    state: _OwnedRoute,
    config: IndexObserverSupervisorConfig,
    spawn_fn: SpawnFn,
    clock_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
) -> _OwnedRoute:
    if not state.ready:
        return state
    observed_ms = _runtime_heartbeat_ms(_json_object(state.route.status))
    maximum_age_ms = int(config.maximum_status_silence_seconds * 1_000)
    if observed_ms is not None and clock_ms_fn() - observed_ms <= maximum_age_ms:
        return state
    _stop_process(state.process, config.stop_timeout_seconds)
    return _restart_route(
        state, config, spawn_fn, clock_ms_fn, monotonic_fn, "status silence"
    )


def _restart_route(
    state: _OwnedRoute,
    config: IndexObserverSupervisorConfig,
    spawn_fn: SpawnFn,
    clock_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
    reason: str,
) -> _OwnedRoute:
    stable_seconds = monotonic_fn() - state.started_monotonic
    prior_restarts = (
        0
        if stable_seconds >= config.restart_budget_reset_seconds
        else state.restart_count
    )
    if prior_restarts >= config.maximum_restarts_per_route:
        raise IndexObserverSupervisorError(
            f"{state.route.symbol} observer exhausted restart budget after {reason}"
        )
    return _start_route(
        state.route,
        spawn_fn,
        clock_ms_fn,
        monotonic_fn,
        prior_restarts + 1,
    )


def _mark_ready(
    owned: tuple[_OwnedRoute, ...],
    config: IndexObserverSupervisorConfig,
    health_check: HealthCheck,
    clock_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
    publication_incomplete_since: float | None,
) -> tuple[tuple[_OwnedRoute, ...], float | None]:
    pending = tuple(state for state in owned if not state.ready)
    if not pending:
        return _validated_health(
            owned,
            config,
            health_check,
            clock_ms_fn,
            monotonic_fn,
            publication_incomplete_since,
        )
    advanced = tuple(state for state in pending if _status_advanced(state))
    for state in advanced:
        _require_preserved_state(state)
    ready = tuple(
        replace(state, ready=True) if state in advanced else state for state in owned
    )
    if not all(state.ready for state in ready):
        return ready, None
    return _validated_health(
        ready,
        config,
        health_check,
        clock_ms_fn,
        monotonic_fn,
        publication_incomplete_since,
    )


def _validated_health(
    owned: tuple[_OwnedRoute, ...],
    config: IndexObserverSupervisorConfig,
    health_check: HealthCheck,
    clock_ms_fn: Callable[[], int],
    monotonic_fn: Callable[[], float],
    publication_incomplete_since: float | None,
) -> tuple[tuple[_OwnedRoute, ...], float | None]:
    now_ms = clock_ms_fn()
    try:
        health_check(datetime.fromtimestamp(now_ms / 1_000, tz=timezone.utc))
    except Hip3ObserverUnavailableError as exc:
        if exc.reason != _MIXED_PUBLICATION_REASON:
            raise
        started = monotonic_fn()
        if publication_incomplete_since is not None:
            started = publication_incomplete_since
        if monotonic_fn() - started >= config.maximum_status_silence_seconds:
            raise IndexObserverSupervisorError(
                "index observer checkpoint publication remained incomplete"
            ) from exc
        return owned, started
    return owned, None


def _status_advanced(state: _OwnedRoute) -> bool:
    value = _optional_integer(_json_object(state.route.status).get("observed_at_ms"))
    return value is not None and value > max(state.started_ms, state.prior_status_ms)


def _require_preserved_state(state: _OwnedRoute) -> None:
    boundary = _optional_integer(
        _json_object(state.route.cursor).get("decision_time_ms")
    )
    if boundary is None:
        raise IndexObserverSupervisorError(
            f"{state.route.symbol} observer cursor is unavailable after restart"
        )
    if (
        state.prior_cursor_boundary is not None
        and boundary < state.prior_cursor_boundary
    ):
        raise IndexObserverSupervisorError(
            f"{state.route.symbol} observer cursor regressed during restart"
        )
    if not _read_bytes(state.route.journal).startswith(state.prior_journal):
        raise IndexObserverSupervisorError(
            f"{state.route.symbol} observer journal changed non-append-only"
        )


def _stop_children(owned: tuple[_OwnedRoute, ...], timeout: float) -> None:
    running = tuple(state for state in owned if state.process.poll() is None)
    for state in running:
        state.process.terminate()
    for state in running:
        _wait_or_kill(state.process, timeout)


def _stop_process(process: ObserverProcess, timeout: float) -> None:
    if process.poll() is None:
        process.terminate()
        _wait_or_kill(process, timeout)


def _wait_or_kill(process: ObserverProcess, timeout: float) -> None:
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _spawn_observer(route: IndexObserverRoute) -> ObserverProcess:
    route.log.parent.mkdir(parents=True, exist_ok=True)
    with route.log.open("ab", buffering=0) as stream:
        return subprocess.Popen(route.command, stdout=stream, stderr=subprocess.STDOUT)


def _write_status(
    config: IndexObserverSupervisorConfig,
    owned: tuple[_OwnedRoute, ...],
    observed_at_ms: int,
    *,
    status: str | None = None,
    health_issue: str | None = None,
) -> None:
    payload = _status_payload(config, owned, observed_at_ms)
    if health_issue is not None:
        payload["health_issue"] = health_issue
    payload["status"] = (
        status
        if status is not None
        else "degraded"
        if health_issue is not None
        else "ready"
        if all(state.ready for state in owned)
        else "warming"
    )
    _publish_status(config.status, payload)


def _status_payload(
    config: IndexObserverSupervisorConfig,
    owned: tuple[_OwnedRoute, ...],
    observed_at_ms: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hip3_index_observer_supervisor",
        "observed_at_ms": observed_at_ms,
        "maximum_status_silence_seconds": config.maximum_status_silence_seconds,
        "restart_budget_reset_seconds": config.restart_budget_reset_seconds,
        "execution_authority": "none",
        "report_only": True,
        "orders_supported": False,
        "routes": [
            {
                "symbol": state.route.symbol,
                "ready": state.ready,
                "restart_count": state.restart_count,
            }
            for state in owned
        ],
    }


def _publish_status(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _write_fault_status(
    config: IndexObserverSupervisorConfig,
    owned: tuple[_OwnedRoute, ...],
    error: str,
    observed_at_ms: int,
) -> None:
    payload = _status_payload(config, owned, observed_at_ms)
    payload.update(
        {
            "status": "fault",
            "error": error,
        }
    )
    _publish_status(config.status, payload)


def _validate_routes(
    supervisor_status: Path, routes: tuple[IndexObserverRoute, ...]
) -> None:
    symbols = tuple(route.symbol for route in routes)
    if len(routes) != 2 or set(symbols) != {"xyz:SP500", "xyz:SPCX"}:
        raise ValueError("index observer supervisor requires exact SP500/SPCX pair")
    paths = [
        path
        for route in routes
        for path in (route.status, route.cursor, route.journal, route.log)
    ]
    if len(paths) != len(set(paths)):
        raise ValueError("index observer supervisor route files must be distinct")
    if supervisor_status in paths:
        raise ValueError("index observer supervisor status must be distinct")


def _json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise IndexObserverSupervisorError(f"observer state is not an object: {path}")
    return value


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IndexObserverSupervisorError("observer state integer is invalid")
    return value


def _runtime_heartbeat_ms(status: dict[str, object]) -> int | None:
    """Return process liveness separately from last successful market data."""
    runtime = status.get("observer_runtime")
    if runtime is None:
        return _optional_integer(status.get("observed_at_ms"))
    if not isinstance(runtime, dict):
        raise IndexObserverSupervisorError("observer runtime state is invalid")
    attempt = _optional_integer(runtime.get("last_attempt_observed_at_ms"))
    if attempt is not None:
        return attempt
    return _optional_integer(status.get("observed_at_ms"))


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return b""
