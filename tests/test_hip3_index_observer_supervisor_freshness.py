"""Continuous freshness tests for the report-only index observer supervisor."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import pytest

from hypervector.live.hip3_index_observer_supervisor import (
    IndexObserverRoute,
    IndexObserverSupervisorConfig,
    supervise_index_observers,
)
from hypervector.live.hip3_provider_availability import (
    Hip3ObserverUnavailableError,
)


class _RunningProcess:
    """Minimal running child that supports graceful supervisor cleanup."""

    def __init__(self, exits: tuple[int | None, ...] = ()) -> None:
        self._exits = list(exits)
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        """Return the current process status."""
        if self._exits:
            self.returncode = self._exits.pop(0)
        return self.returncode

    def terminate(self) -> None:
        """Record graceful termination."""
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        """Return the terminal status without blocking."""
        del timeout
        return 0 if self.returncode is None else self.returncode

    def kill(self) -> None:
        """Record forced termination for protocol completeness."""
        self.returncode = -9


def test_ready_children_continue_to_run_the_freshness_contract(tmp_path: Path) -> None:
    """A live-but-stale observer must fault after initial readiness."""
    routes = _routes(tmp_path)
    health_calls = 0
    cycles = 0

    def spawn(route: IndexObserverRoute) -> _RunningProcess:
        route.status.write_text(json.dumps({"observed_at_ms": 1_000_001}))
        route.cursor.write_text(json.dumps({"decision_time_ms": 900}))
        return _RunningProcess()

    def health_check(_now: datetime) -> None:
        nonlocal health_calls
        health_calls += 1
        if health_calls == 2:
            raise ValueError("observer stale after ready")

    def sleep(_seconds: float) -> None:
        nonlocal cycles
        cycles += 1

    with pytest.raises(ValueError, match="stale after ready"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(
                status=tmp_path / "supervisor.json", poll_seconds=0.1
            ),
            routes,
            spawn_fn=spawn,
            owner_active_fn=lambda _path: False,
            health_check=health_check,
            clock_ms_fn=lambda: 1_000_000,
            sleep_fn=sleep,
            stop_requested=lambda: cycles >= 3,
        )

    assert health_calls == 2
    status = json.loads((tmp_path / "supervisor.json").read_text())
    assert status["status"] == "fault"


def test_stale_running_child_restarts_without_its_fresh_sibling(tmp_path: Path) -> None:
    """Status silence restarts only the affected live child."""
    routes = _routes(tmp_path)
    now_ms = 1_000_000
    spawned: dict[str, list[_RunningProcess]] = {route.symbol: [] for route in routes}

    def spawn(route: IndexObserverRoute) -> _RunningProcess:
        process = _RunningProcess()
        spawned[route.symbol].append(process)
        route.status.write_text(json.dumps({"observed_at_ms": now_ms + 1}))
        route.cursor.write_text(json.dumps({"decision_time_ms": 900}))
        return process

    def sleep(seconds: float) -> None:
        nonlocal now_ms
        now_ms += int(seconds * 1_000)
        routes[1].status.write_text(json.dumps({"observed_at_ms": now_ms + 1}))

    supervise_index_observers(
        IndexObserverSupervisorConfig(
            status=tmp_path / "supervisor.json",
            poll_seconds=5.0,
            maximum_status_silence_seconds=10.0,
        ),
        routes,
        spawn_fn=spawn,
        owner_active_fn=lambda _path: False,
        health_check=lambda _now: None,
        clock_ms_fn=lambda: now_ms,
        sleep_fn=sleep,
        stop_requested=lambda: len(spawned["xyz:SP500"]) == 2 or now_ms >= 1_025_000,
    )

    assert len(spawned["xyz:SP500"]) == 2
    assert len(spawned["xyz:SPCX"]) == 1
    assert spawned["xyz:SP500"][0].terminated is True
    assert spawned["xyz:SPCX"][0].terminated is True


@pytest.mark.parametrize(
    "health_reason",
    ("observer_status_stale", "observer_runtime_degraded_transient"),
)
def test_transient_data_staleness_does_not_restart_a_live_child(
    tmp_path: Path,
    health_reason: str,
) -> None:
    """A current process heartbeat must remain distinct from stale market data."""
    routes = _routes(tmp_path)
    now_ms = 1_000_000
    cycles = 0
    supervisor_states: list[dict[str, object]] = []
    spawned: dict[str, list[_RunningProcess]] = {route.symbol: [] for route in routes}

    def spawn(route: IndexObserverRoute) -> _RunningProcess:
        return _spawn_with_runtime_status(route, spawned, now_ms + 1)

    def health_check(_now: datetime) -> None:
        if cycles:
            raise Hip3ObserverUnavailableError(health_reason)

    def sleep(seconds: float) -> None:
        nonlocal now_ms, cycles
        if status_path.exists():
            supervisor_states.append(json.loads(status_path.read_text()))
        now_ms += int(seconds * 1_000)
        cycles += 1
        for route in routes:
            status = json.loads(route.status.read_text())
            status["observer_runtime"]["last_attempt_observed_at_ms"] = now_ms + 1
            route.status.write_text(json.dumps(status))

    status_path = tmp_path / "supervisor.json"
    supervise_index_observers(
        IndexObserverSupervisorConfig(
            status=status_path,
            poll_seconds=5.0,
            maximum_status_silence_seconds=10.0,
        ),
        routes,
        spawn_fn=spawn,
        owner_active_fn=lambda _path: False,
        health_check=health_check,
        clock_ms_fn=lambda: now_ms,
        sleep_fn=sleep,
        stop_requested=lambda: cycles >= 4,
    )

    _assert_degraded_without_restarts(
        spawned, supervisor_states, status_path, health_reason
    )


def test_warmup_timeout_restarts_only_the_stalled_child(tmp_path: Path) -> None:
    """A transient startup stall consumes its route budget, not the sibling."""
    routes = _routes(tmp_path)
    now_ms = 1_000_000
    spawned: dict[str, list[_RunningProcess]] = {route.symbol: [] for route in routes}

    def spawn(route: IndexObserverRoute) -> _RunningProcess:
        generation = len(spawned[route.symbol])
        process = _RunningProcess()
        spawned[route.symbol].append(process)
        if route.symbol == "xyz:SP500" or generation > 0:
            route.status.write_text(json.dumps({"observed_at_ms": now_ms + 1}))
            route.cursor.write_text(json.dumps({"decision_time_ms": 900}))
        return process

    def sleep(seconds: float) -> None:
        nonlocal now_ms
        now_ms += int(seconds * 1_000)

    status_path = tmp_path / "supervisor.json"
    supervise_index_observers(
        IndexObserverSupervisorConfig(
            status=status_path,
            poll_seconds=0.1,
            warmup_seconds=0.2,
        ),
        routes,
        spawn_fn=spawn,
        owner_active_fn=lambda _path: False,
        health_check=lambda _now: None,
        clock_ms_fn=lambda: now_ms,
        monotonic_fn=lambda: (now_ms - 1_000_000) / 1_000.0,
        sleep_fn=sleep,
        stop_requested=lambda: len(spawned["xyz:SPCX"]) == 2,
    )

    status = json.loads(status_path.read_text())
    assert len(spawned["xyz:SP500"]) == 1
    assert len(spawned["xyz:SPCX"]) == 2
    assert spawned["xyz:SPCX"][0].terminated is True
    assert all(route["ready"] for route in status["routes"])


def test_restart_budget_resets_after_a_stable_recovery_window(
    tmp_path: Path,
) -> None:
    """Separated transient stalls must not exhaust one lifetime-wide budget."""
    routes = _routes(tmp_path)
    now_ms = 1_000_000
    spawned: dict[str, list[_RunningProcess]] = {route.symbol: [] for route in routes}

    def spawn(route: IndexObserverRoute) -> _RunningProcess:
        generation = len(spawned[route.symbol])
        exits: tuple[int | None, ...] = ()
        if route.symbol == "xyz:SP500":
            exits = (None, 7) if generation == 0 else (None,) * 60 + (7,)
        process = _RunningProcess(exits)
        spawned[route.symbol].append(process)
        route.status.write_text(json.dumps({"observed_at_ms": now_ms + 1}))
        route.cursor.write_text(json.dumps({"decision_time_ms": 900}))
        return process

    def sleep(seconds: float) -> None:
        nonlocal now_ms
        now_ms += int(seconds * 1_000)

    supervise_index_observers(
        IndexObserverSupervisorConfig(
            status=tmp_path / "supervisor.json",
            poll_seconds=0.1,
            maximum_restarts_per_route=1,
            restart_budget_reset_seconds=5.0,
        ),
        routes,
        spawn_fn=spawn,
        owner_active_fn=lambda _path: False,
        health_check=lambda _now: None,
        clock_ms_fn=lambda: now_ms,
        monotonic_fn=lambda: (now_ms - 1_000_000) / 1_000.0,
        sleep_fn=sleep,
        stop_requested=lambda: len(spawned["xyz:SP500"]) == 3,
    )

    assert len(spawned["xyz:SP500"]) == 3
    assert len(spawned["xyz:SPCX"]) == 1


def _routes(tmp_path: Path) -> tuple[IndexObserverRoute, ...]:
    return tuple(
        IndexObserverRoute(
            symbol=symbol,
            command=("observer", symbol),
            status=tmp_path / f"{token}.status.json",
            cursor=tmp_path / f"{token}.cursor.json",
            journal=tmp_path / f"{token}.jsonl",
            log=tmp_path / f"{token}.log",
        )
        for symbol, token in (("xyz:SP500", "sp500"), ("xyz:SPCX", "spcx"))
    )


def _spawn_with_runtime_status(
    route: IndexObserverRoute,
    spawned: dict[str, list[_RunningProcess]],
    observed_at_ms: int,
) -> _RunningProcess:
    """Start a fake child and publish one explicit runtime heartbeat."""
    process = _RunningProcess()
    spawned[route.symbol].append(process)
    route.status.write_text(
        json.dumps(
            {
                "observed_at_ms": observed_at_ms,
                "observer_runtime": {
                    "last_attempt_observed_at_ms": observed_at_ms,
                },
            }
        )
    )
    route.cursor.write_text(json.dumps({"decision_time_ms": 900}))
    return process


def _assert_degraded_without_restarts(
    spawned: dict[str, list[_RunningProcess]],
    states: list[dict[str, object]],
    status_path: Path,
    health_reason: str,
) -> None:
    """Require a recoverable health gap without process churn."""
    assert all(len(processes) == 1 for processes in spawned.values())
    assert any(
        status.get("status") == "degraded"
        and status.get("health_issue") == health_reason
        for status in states
    )
    assert json.loads(status_path.read_text())["status"] == "stopped"
