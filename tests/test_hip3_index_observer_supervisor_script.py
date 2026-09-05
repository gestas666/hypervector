"""CLI boundary tests for the report-only HIP-3 index observer supervisor."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import FrameType
from types import ModuleType
from typing import Iterator

import pytest

from hypervector.live.hip3_index_observer_supervisor import (
    IndexObserverRoute,
    IndexObserverSupervisorConfig,
)

_SCRIPT = Path("scripts/hip3_index_observer_supervisor.py")


def test_script_owns_only_the_two_unsigned_index_observer_commands() -> None:
    """The standalone supervisor has no live-arm or order-client surface."""
    assert _SCRIPT.is_file()
    source = _SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "--enabled",
        "--i-accept-live-risk",
        "HyperliquidOrderClient",
        "API_PRIVATE_KEY",
    )
    assert all(value not in source for value in forbidden)
    routes = _module().default_routes()
    assert tuple(route.symbol for route in routes) == ("xyz:SP500", "xyz:SPCX")
    assert all(
        route.command[-2:] == ("--symbol", route.symbol)
        and "index_hip3_breakout_shadow_observe.py" in route.command[-3]
        for route in routes
    )


def test_main_holds_a_singleton_lock_while_supervising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only one supervisor may own the bounded status and child pair."""
    module = _module()
    status = tmp_path / "supervisor.json"
    events: list[str] = []

    @contextmanager
    def lock(path: Path) -> Iterator[Path]:
        assert path == status
        events.append("lock_enter")
        yield path.with_suffix(".lock")
        events.append("lock_exit")

    def supervise(
        config: IndexObserverSupervisorConfig,
        routes: tuple[IndexObserverRoute, ...],
        *,
        stop_requested: Callable[[], bool],
    ) -> int:
        assert config.status == status
        assert tuple(route.symbol for route in routes) == ("xyz:SP500", "xyz:SPCX")
        assert stop_requested() is False
        events.append("supervise")
        return 0

    monkeypatch.setattr(module, "cohort_checkpoint_runtime_lock", lock)
    monkeypatch.setattr(module, "supervise_index_observers", supervise)

    assert module.main(["--status", str(status)]) == 0
    assert events == ["lock_enter", "supervise", "lock_exit"]


def test_main_translates_sigterm_into_a_clean_supervisor_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGTERM requests graceful child shutdown and restores prior handlers."""
    module = _module()
    signal_handler = Callable[[int, FrameType | None], None] | str
    handlers: dict[int, signal_handler] = {
        module.signal.SIGINT: "prior-int",
        module.signal.SIGTERM: "prior-term",
    }

    def install(signum: int, handler: signal_handler) -> signal_handler:
        previous = handlers[signum]
        handlers[signum] = handler
        return previous

    def supervise(
        _config: IndexObserverSupervisorConfig,
        _routes: tuple[IndexObserverRoute, ...],
        *,
        stop_requested: Callable[[], bool],
    ) -> int:
        assert stop_requested() is False
        handler = handlers[module.signal.SIGTERM]
        assert callable(handler)
        handler(module.signal.SIGTERM, None)
        assert stop_requested() is True
        return 0

    monkeypatch.setattr(module.signal, "signal", install)
    monkeypatch.setattr(module, "cohort_checkpoint_runtime_lock", _passthrough_lock)
    monkeypatch.setattr(module, "supervise_index_observers", supervise)

    assert module.main(["--status", str(tmp_path / "status.json")]) == 0
    assert handlers[module.signal.SIGINT] == "prior-int"
    assert handlers[module.signal.SIGTERM] == "prior-term"


@contextmanager
def _passthrough_lock(path: Path) -> Iterator[Path]:
    yield path


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "hip3_index_observer_supervisor", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("supervisor script module spec is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
