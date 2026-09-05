"""One-command TUI dependency lifecycle for the V79 SPCX route."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from hypervector.live.cohort_tui_commands import index_observer_dependency_command
from hypervector.live.hip3_provider_availability import (
    Hip3ObserverUnavailableError,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_CONFIG = Path("configs/multi_asset_growth_first_5000_seven_asset_all_active_v79.toml")
_SCRIPT = Path("scripts/multi_asset_bidirectional_canary_tui.py")


def test_v79_dependency_command_starts_only_unsigned_spcx_observer() -> None:
    """The one-command launcher must not revive SP500 or expose order flags."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")

    command = index_observer_dependency_command(config)

    assert command is not None
    assert "scripts/index_hip3_breakout_shadow_observe.py" in command
    assert command[-2:] == ("--symbol", "xyz:SPCX")
    assert "xyz:SP500" not in command
    assert "--enabled" not in command
    assert "--i-accept-live-risk" not in command


def test_dependency_start_waits_for_fresh_health_and_returns_owned_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale observer is started and proven fresh before backend launch."""
    module = _load_script()
    health = iter((False, True))
    process = SimpleNamespace(poll=lambda: None, returncode=None)
    monkeypatch.setattr(module, "_DEPENDENCY_LOG", tmp_path / "dependency.log")
    monkeypatch.setattr(
        module,
        "_require_live_provider_dependencies",
        lambda _config: (
            None
            if next(health)
            else (_ for _ in ()).throw(
                Hip3ObserverUnavailableError("observer_status_stale")
            )
        ),
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )

    result = module._start_owned_dependency(
        ("python", "observer.py"),
        SimpleNamespace(),
        timeout_seconds=1.0,
    )

    assert result is process


def _load_script() -> ModuleType:
    spec = spec_from_file_location("v79_tui_dependency_launcher", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
