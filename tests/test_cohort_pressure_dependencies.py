"""Unsigned multi-observer startup keeps ownership and dependency scope exact."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hypervector.live.hip3_breakout_shadow_specs import SNDK_SHADOW_SPEC
from hypervector.live.hip3_provider_availability import Hip3ObserverUnavailableError
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live import cohort_pressure_dependencies as dependencies
from hypervector.live import cohort_dependency_supervision as supervision

_CONFIG = Path(
    "tests/fixtures/profiles/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)
_OLD = "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3"


def test_only_corrected_sndk_adds_its_unsigned_dependency() -> None:
    """The V86 baseline retains SPCX-only supervision; v4 adds exactly SNDK."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    assert set(dependencies.pressure_dependency_commands(config)) == {"xyz:SPCX"}
    config = replace(
        config,
        providers=tuple(
            replace(row, strategy_id=SNDK_SHADOW_SPEC.provider_id)
            if row.strategy_id == _OLD
            else row
            for row in config.providers
        ),
    )
    commands = dependencies.pressure_dependency_commands(config)
    assert set(commands) == {"xyz:SPCX", "xyz:SNDK"}
    assert all("--enabled" not in command for command in commands.values())
    assert all("--i-accept-live-risk" not in command for command in commands.values())


@pytest.mark.parametrize("failure", [False, True])
def test_group_cleans_only_processes_it_started(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: bool,
) -> None:
    """Partial startup failure closes owned children and preserves reused ones."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    first = SimpleNamespace(poll=lambda: None)
    stopped = []
    monkeypatch.setattr(
        dependencies,
        "pressure_dependency_commands",
        lambda _config: {"xyz:SPCX": ("first",), "xyz:SNDK": ("second",)},
    )

    def start(command: tuple[str, ...], *args: object, **kwargs: object) -> object:
        if command == ("first",):
            return first
        if failure:
            raise RuntimeError("second source failed")
        return None

    monkeypatch.setattr(dependencies, "start_owned_dependency", start)
    monkeypatch.setattr(dependencies, "stop_owned_dependency", stopped.append)
    if failure:
        with pytest.raises(RuntimeError, match="second source failed"):
            dependencies.run_pressure_dependencies(
                config, log_root=tmp_path, stop_requested=lambda: True
            )
    else:
        dependencies.run_pressure_dependencies(
            config, log_root=tmp_path, stop_requested=lambda: True
        )
    assert stopped == [first]


def test_source_validation_error_during_startup_reaps_owned_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A newly started observer cannot leak when its initial health file is invalid."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    process = SimpleNamespace(poll=lambda: None)
    stopped = []
    calls = 0

    def health(_config: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FileNotFoundError("observer absent")
        raise ValueError("observer identity corrupt")

    monkeypatch.setattr(
        supervision.subprocess, "Popen", lambda *args, **kwargs: process
    )
    monkeypatch.setattr(supervision, "stop_owned_dependency", stopped.append)
    with pytest.raises(ValueError, match="identity corrupt"):
        supervision.start_owned_dependency(
            ("observer",),
            config,
            timeout_seconds=1,
            log_path=tmp_path / "observer.log",
            health_check=health,
        )
    assert stopped == [process]


def test_temporary_staleness_preserves_collector_until_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stale data remain unavailable while the owned collector can recover."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    process = SimpleNamespace(poll=lambda: None)
    stopped = []
    attempts = []
    monkeypatch.setattr(dependencies, "start_owned_dependency", lambda *a, **k: process)
    monkeypatch.setattr(dependencies, "stop_owned_dependency", stopped.append)
    monkeypatch.setattr(dependencies.time, "sleep", lambda _: None)

    def health(symbol: str, _config: object) -> None:
        assert not stopped
        attempts.append(symbol)
        if len(attempts) == 1:
            raise Hip3ObserverUnavailableError("observer_status_stale")

    monkeypatch.setattr(dependencies, "_require_symbol_health", health)
    dependencies.run_pressure_dependencies(
        config, log_root=tmp_path, stop_requested=lambda: len(attempts) == 2
    )
    assert stopped == [process]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event["status"] for event in events] == ["unavailable", "recovered"]
    assert events[0]["reason"] == "observer_status_stale"
    assert all(event["execution_authority"] == "none" for event in events)


def test_exited_owned_collector_still_aborts_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dead source is a lifecycle failure, not transient data staleness."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    process = SimpleNamespace(poll=lambda: 1)
    stopped = []
    monkeypatch.setattr(dependencies, "start_owned_dependency", lambda *a, **k: process)
    monkeypatch.setattr(dependencies, "stop_owned_dependency", stopped.append)
    with pytest.raises(ValueError, match="dependency exited"):
        dependencies.run_pressure_dependencies(
            config, log_root=tmp_path, stop_requested=lambda: False
        )
    assert stopped == [process]
