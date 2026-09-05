"""Crash-recovery tests for the report-only HIP-3 index observer supervisor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path

import pytest

from hypervector.live.hip3_index_observer_supervisor import (
    IndexObserverRoute,
    IndexObserverSupervisorConfig,
    IndexObserverSupervisorError,
    supervise_index_observers,
)
from hypervector.live.hip3_provider_availability import (
    Hip3ObserverUnavailableError,
)


class _Clock:
    """Deterministic clock shared by the supervisor and fake children."""

    def __init__(self) -> None:
        self.elapsed = 0.0

    def monotonic(self) -> float:
        """Return deterministic elapsed seconds."""
        return self.elapsed

    def epoch_ms(self) -> int:
        """Return a deterministic positive wall-clock timestamp."""
        return 1_000_000 + int(self.elapsed * 1_000)

    def sleep(self, seconds: float) -> None:
        """Advance deterministic time without blocking the test."""
        self.elapsed += seconds


class _Process:
    """Small controllable process surface matching ``subprocess.Popen``."""

    def __init__(self, exits: tuple[int | None, ...]) -> None:
        self._exits = list(exits)
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        """Return the next configured child state."""
        if self._exits:
            self.returncode = self._exits.pop(0)
        return self.returncode

    def terminate(self) -> None:
        """Record a graceful stop request."""
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        """Return the terminal status without blocking."""
        del timeout
        return 0 if self.returncode is None else self.returncode

    def kill(self) -> None:
        """Record forced termination for protocol completeness."""
        self.terminated = True
        self.returncode = -9


def test_failed_route_restarts_without_restarting_healthy_sibling(
    tmp_path: Path,
) -> None:
    """One observer crash preserves both cursors and restarts only that route."""
    clock = _Clock()
    routes = _routes(tmp_path)
    for route in routes:
        _write_state(route.status, route.cursor, observed_ms=900_000, boundary=900)
        route.journal.write_text('{"event_id":"preserved"}\n', encoding="utf-8")
    spawned: dict[str, list[_Process]] = {route.symbol: [] for route in routes}

    def spawn(route: IndexObserverRoute) -> _Process:
        generation = len(spawned[route.symbol])
        exits = (None, 17) if route.symbol == "xyz:SP500" and generation == 0 else ()
        process = _Process(exits)
        spawned[route.symbol].append(process)
        _write_state(
            route.status,
            route.cursor,
            observed_ms=clock.epoch_ms() + 1,
            boundary=900,
        )
        return process

    config = IndexObserverSupervisorConfig(
        status=tmp_path / "supervisor.json",
        poll_seconds=0.1,
        stop_timeout_seconds=1.0,
    )
    supervise_index_observers(
        config,
        routes,
        spawn_fn=spawn,
        health_check=lambda _now: None,
        clock_ms_fn=clock.epoch_ms,
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
        stop_requested=_stop_after(clock, 0.4),
    )
    assert (len(spawned["xyz:SP500"]), len(spawned["xyz:SPCX"])) == (2, 1)
    assert spawned["xyz:SP500"][0].returncode == 17
    assert spawned["xyz:SP500"][1].terminated is True
    assert spawned["xyz:SPCX"][0].terminated is True
    assert json.loads(routes[0].cursor.read_text())["decision_time_ms"] == 900
    assert routes[0].journal.read_text() == '{"event_id":"preserved"}\n'
    status = json.loads(config.status.read_text())
    assert (status["status"], status["execution_authority"]) == ("stopped", "none")
    assert status["observed_at_ms"] == clock.epoch_ms()
    assert status["maximum_status_silence_seconds"] == 20.0
    assert status["routes"][0]["restart_count"] == 1


def test_transient_mixed_publication_degrades_then_recovers(
    tmp_path: Path,
) -> None:
    """One journal/status/cursor race must not terminate both observers."""
    clock = _Clock()
    routes = _routes(tmp_path)
    children: list[_Process] = []
    observed_statuses: list[dict[str, object]] = []
    health_calls = 0

    def spawn(route: IndexObserverRoute) -> _Process:
        process = _Process(())
        children.append(process)
        _write_state(
            route.status,
            route.cursor,
            observed_ms=clock.epoch_ms() + 1,
            boundary=900,
        )
        return process

    def health_check(_now: datetime) -> None:
        nonlocal health_calls
        health_calls += 1
        if health_calls == 2:
            raise Hip3ObserverUnavailableError(
                "observer_checkpoint_publication_incomplete"
            )

    def observe_sleep(seconds: float) -> None:
        observed_statuses.append(json.loads(config.status.read_text()))
        clock.sleep(seconds)

    config = IndexObserverSupervisorConfig(
        status=tmp_path / "supervisor.json",
        poll_seconds=0.1,
        maximum_status_silence_seconds=0.3,
    )
    result = supervise_index_observers(
        config,
        routes,
        spawn_fn=spawn,
        owner_active_fn=lambda _path: False,
        health_check=health_check,
        clock_ms_fn=clock.epoch_ms,
        monotonic_fn=clock.monotonic,
        sleep_fn=observe_sleep,
        stop_requested=_stop_after(clock, 0.4),
    )

    assert result == 0
    assert health_calls >= 3
    assert [row["status"] for row in observed_statuses][:3] == [
        "ready",
        "degraded",
        "ready",
    ]
    assert observed_statuses[1]["health_issue"] == (
        "observer_checkpoint_publication_incomplete"
    )
    assert all(child.terminated for child in children)


def test_persistent_mixed_publication_faults_after_bounded_window(
    tmp_path: Path,
) -> None:
    """A permanently incoherent checkpoint must still fail explicitly."""
    clock = _Clock()
    routes = _routes(tmp_path)

    def spawn(route: IndexObserverRoute) -> _Process:
        _write_state(
            route.status,
            route.cursor,
            observed_ms=clock.epoch_ms() + 1,
            boundary=900,
        )
        return _Process(())

    def health_check(_now: datetime) -> None:
        raise Hip3ObserverUnavailableError("observer_checkpoint_publication_incomplete")

    config = IndexObserverSupervisorConfig(
        status=tmp_path / "supervisor.json",
        poll_seconds=0.1,
        maximum_status_silence_seconds=0.2,
    )
    with pytest.raises(
        IndexObserverSupervisorError,
        match="checkpoint publication remained incomplete",
    ):
        supervise_index_observers(
            config,
            routes,
            spawn_fn=spawn,
            owner_active_fn=lambda _path: False,
            health_check=health_check,
            clock_ms_fn=clock.epoch_ms,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        )

    status = json.loads(config.status.read_text())
    assert status["status"] == "fault"
    assert "publication remained incomplete" in status["error"]


def test_existing_observer_owner_is_refused_before_any_child_starts(
    tmp_path: Path,
) -> None:
    """A supervisor cannot overlap manually owned observer status files."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        IndexObserverSupervisorError,
        supervise_index_observers,
    )

    routes = _routes(tmp_path)
    spawned: list[str] = []

    with pytest.raises(IndexObserverSupervisorError, match="already owns"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(status=tmp_path / "supervisor.json"),
            routes,
            spawn_fn=lambda route: spawned.append(route.symbol),
            owner_active_fn=lambda path: path == routes[0].status,
        )

    assert spawned == []
    supervisor = json.loads((tmp_path / "supervisor.json").read_text())
    assert supervisor["status"] == "fault"
    assert "already owns" in supervisor["error"]


def test_restarted_observer_fails_closed_if_its_cursor_regresses(
    tmp_path: Path,
) -> None:
    """A replacement cannot discard an already preserved decision boundary."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        IndexObserverSupervisorError,
        supervise_index_observers,
    )

    clock = _Clock()
    routes = _routes(tmp_path)
    spawned: dict[str, list[_Process]] = {route.symbol: [] for route in routes}
    for route in routes:
        _write_state(route.status, route.cursor, observed_ms=900_000, boundary=900)

    def spawn(route: IndexObserverRoute) -> _Process:
        symbol = route.symbol
        generation = len(spawned[symbol])
        process = _Process(
            (None, 9) if symbol == "xyz:SP500" and not generation else ()
        )
        spawned[symbol].append(process)
        boundary = 899 if symbol == "xyz:SP500" and generation else 900
        _write_state(
            route.status,
            route.cursor,
            observed_ms=clock.epoch_ms() + 1,
            boundary=boundary,
        )
        return process

    with pytest.raises(IndexObserverSupervisorError, match="cursor regressed"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(
                status=tmp_path / "supervisor.json",
                poll_seconds=0.1,
            ),
            routes,
            spawn_fn=spawn,
            owner_active_fn=lambda _path: False,
            health_check=lambda _now: None,
            clock_ms_fn=clock.epoch_ms,
            sleep_fn=clock.sleep,
        )

    supervisor = json.loads((tmp_path / "supervisor.json").read_text())
    assert supervisor["status"] == "fault"
    assert supervisor["observed_at_ms"] == clock.epoch_ms()
    assert "cursor regressed" in supervisor["error"]


def test_restarted_observer_fails_closed_if_journal_is_replaced(
    tmp_path: Path,
) -> None:
    """Crash recovery cannot truncate or replace prior prospective evidence."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        IndexObserverSupervisorError,
        supervise_index_observers,
    )

    clock = _Clock()
    routes = _routes(tmp_path)
    spawned: dict[str, list[_Process]] = {route.symbol: [] for route in routes}
    for route in routes:
        _write_state(route.status, route.cursor, observed_ms=900_000, boundary=900)
        route.journal.write_text('{"event_id":"preserved"}\n', encoding="utf-8")

    def spawn(route: IndexObserverRoute) -> _Process:
        generation = len(spawned[route.symbol])
        process = _Process(
            (None, 9) if route.symbol == "xyz:SP500" and not generation else ()
        )
        spawned[route.symbol].append(process)
        _write_state(
            route.status,
            route.cursor,
            observed_ms=clock.epoch_ms() + 1,
            boundary=900,
        )
        if route.symbol == "xyz:SP500" and generation:
            route.journal.write_text('{"event_id":"replacement"}\n', encoding="utf-8")
        return process

    with pytest.raises(IndexObserverSupervisorError, match="journal changed"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(
                status=tmp_path / "supervisor.json", poll_seconds=0.1
            ),
            routes,
            spawn_fn=spawn,
            owner_active_fn=lambda _path: False,
            health_check=lambda _now: None,
            clock_ms_fn=clock.epoch_ms,
            sleep_fn=clock.sleep,
            stop_requested=_stop_after(clock, 0.5),
        )


def test_fresh_children_must_pass_the_exact_prospective_health_contract(
    tmp_path: Path,
) -> None:
    """A replacement cannot become ready with retroactive journal evidence."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        supervise_index_observers,
    )

    clock = _Clock()
    routes = _routes(tmp_path)
    children: list[_Process] = []

    def spawn(route: IndexObserverRoute) -> _Process:
        process = _Process(())
        children.append(process)
        _write_state(
            route.status,
            route.cursor,
            observed_ms=clock.epoch_ms() + 1,
            boundary=900,
        )
        return process

    def reject_retroactive(_now: datetime) -> None:
        raise ValueError("HIP-3 v3 decision is not prospective")

    with pytest.raises(ValueError, match="not prospective"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(status=tmp_path / "supervisor.json"),
            routes,
            spawn_fn=spawn,
            owner_active_fn=lambda _path: False,
            health_check=reject_retroactive,
            clock_ms_fn=clock.epoch_ms,
        )

    assert all(child.terminated for child in children)


def test_running_child_without_fresh_status_fails_after_bounded_warmup(
    tmp_path: Path,
) -> None:
    """A hung child cannot leave the supervisor success-shaped indefinitely."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        IndexObserverSupervisorError,
        supervise_index_observers,
    )

    clock = _Clock()
    children: list[_Process] = []

    def spawn(_route: IndexObserverRoute) -> _Process:
        process = _Process(())
        children.append(process)
        return process

    with pytest.raises(IndexObserverSupervisorError, match="restart budget.*warmup"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(
                status=tmp_path / "supervisor.json",
                poll_seconds=0.1,
                warmup_seconds=0.2,
                maximum_restarts_per_route=0,
            ),
            _routes(tmp_path),
            spawn_fn=spawn,
            owner_active_fn=lambda _path: False,
            clock_ms_fn=clock.epoch_ms,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        )

    assert all(child.terminated for child in children)


def test_repeated_child_failures_exhaust_a_bounded_restart_budget(
    tmp_path: Path,
) -> None:
    """A persistent crash loop becomes an explicit supervisor fault."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        IndexObserverSupervisorError,
        supervise_index_observers,
    )

    clock = _Clock()
    routes = _routes(tmp_path)
    spawned: dict[str, list[_Process]] = {route.symbol: [] for route in routes}

    def spawn(route: IndexObserverRoute) -> _Process:
        process = _Process((7,) if route.symbol == "xyz:SP500" else ())
        spawned[route.symbol].append(process)
        _write_state(
            route.status,
            route.cursor,
            observed_ms=clock.epoch_ms() + 1,
            boundary=900,
        )
        return process

    with pytest.raises(IndexObserverSupervisorError, match="restart budget"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(
                status=tmp_path / "supervisor.json",
                poll_seconds=0.1,
                maximum_restarts_per_route=2,
            ),
            routes,
            spawn_fn=spawn,
            owner_active_fn=lambda _path: False,
            health_check=lambda _now: None,
            clock_ms_fn=clock.epoch_ms,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
            stop_requested=_stop_after(clock, 0.5),
        )

    assert len(spawned["xyz:SP500"]) == 3
    assert len(spawned["xyz:SPCX"]) == 1


def test_supervisor_requires_one_exact_route_for_each_index_symbol(
    tmp_path: Path,
) -> None:
    """Partial or duplicated route sets cannot claim pair supervision."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        supervise_index_observers,
    )

    routes = _routes(tmp_path)

    with pytest.raises(ValueError, match="exact SP500/SPCX pair"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(status=tmp_path / "supervisor.json"),
            (routes[0],),
            spawn_fn=lambda _route: _Process(()),
            owner_active_fn=lambda _path: False,
            stop_requested=lambda: True,
        )


def test_supervisor_rejects_aliased_route_state_files(tmp_path: Path) -> None:
    """The two children cannot share cursor, journal, status, or log ownership."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        supervise_index_observers,
    )

    routes = _routes(tmp_path)
    aliased = (routes[0], replace(routes[1], status=routes[0].status))

    with pytest.raises(ValueError, match="route files must be distinct"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(status=tmp_path / "supervisor.json"),
            aliased,
            spawn_fn=lambda _route: _Process(()),
            owner_active_fn=lambda _path: False,
            stop_requested=lambda: True,
        )


def test_supervisor_status_cannot_alias_a_child_state_file(tmp_path: Path) -> None:
    """Supervisor telemetry cannot overwrite child evidence or ownership state."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
        supervise_index_observers,
    )

    routes = _routes(tmp_path)
    with pytest.raises(ValueError, match="supervisor status must be distinct"):
        supervise_index_observers(
            IndexObserverSupervisorConfig(status=routes[0].status),
            routes,
            spawn_fn=lambda _route: _Process(()),
            owner_active_fn=lambda _path: False,
            stop_requested=lambda: True,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("poll_seconds", 0.0),
        ("warmup_seconds", 0.0),
        ("stop_timeout_seconds", 0.0),
        ("maximum_status_silence_seconds", 0.0),
        ("restart_budget_reset_seconds", 0.0),
        ("poll_seconds", float("nan")),
        ("warmup_seconds", float("inf")),
        ("maximum_restarts_per_route", -1),
        ("maximum_restarts_per_route", True),
    ],
)
def test_supervisor_rejects_unbounded_process_policies(
    tmp_path: Path,
    field: str,
    value: float | int,
) -> None:
    """Durations must be positive and restart budgets nonnegative."""
    from hypervector.live.hip3_index_observer_supervisor import (
        IndexObserverSupervisorConfig,
    )

    values: dict[str, Path | float | int] = {
        "status": tmp_path / "supervisor.json",
        field: value,
    }
    with pytest.raises(ValueError, match="supervisor policy"):
        IndexObserverSupervisorConfig(**values)


def _routes(tmp_path: Path) -> tuple[IndexObserverRoute, ...]:
    return tuple(
        IndexObserverRoute(
            symbol=symbol,
            command=("python", "observer.py", "--symbol", symbol),
            status=tmp_path / f"{token}.status.json",
            cursor=tmp_path / f"{token}.cursor.json",
            journal=tmp_path / f"{token}.jsonl",
            log=tmp_path / f"{token}.log",
        )
        for symbol, token in (("xyz:SP500", "sp500"), ("xyz:SPCX", "spcx"))
    )


def _write_state(
    status: Path,
    cursor: Path,
    *,
    observed_ms: int,
    boundary: int,
) -> None:
    status.write_text(json.dumps({"observed_at_ms": observed_ms}), encoding="utf-8")
    cursor.write_text(
        json.dumps({"decision_time_ms": boundary}),
        encoding="utf-8",
    )


def _stop_after(clock: _Clock, elapsed: float) -> Callable[[], bool]:
    return lambda: clock.elapsed >= elapsed
