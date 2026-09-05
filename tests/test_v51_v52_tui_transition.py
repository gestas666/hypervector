"""Unified-TUI identity checks for active v51 and staged v52."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/multi_asset_bidirectional_canary_tui.py")
_V51 = "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
_V52 = "configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml"


def test_monitor_stages_exact_v52_without_live_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cockpit must show v51 live and v52 staged without arming v52."""
    module = _module()
    monkeypatch.setattr(
        module, "load_required_accounting_epoch", lambda bundle, successor: None
    )
    args = module.build_parser().parse_args(
        ["--mode", "monitor", "--config", _V51, "--staged-config", _V52]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.config.profile_id.endswith("v51")
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id.endswith("v52")
    assert launch.staged_config.symbols == ("BTC", "HYPE")
    assert len(launch.staged_config.executable_provider_symbols) == 3
    assert len(launch.staged_config.executable_provider_directions) == 4
    assert "--enabled" not in launch.tui_command
    assert "--i-accept-live-risk" not in launch.tui_command
    config_index = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[config_index + 1] == _V52


def test_monitor_binds_v52_accounting_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The staged 0/0 epoch must identify v52 rather than active v51."""
    module = _module()
    observed: dict[str, object] = {}

    def load_epoch(bundle: Path | None, successor: object) -> None:
        observed.update(bundle=bundle, profile_id=successor.profile_id)

    monkeypatch.setattr(module, "load_required_accounting_epoch", load_epoch)
    args = module.build_parser().parse_args(
        [
            "--mode",
            "monitor",
            "--config",
            _V51,
            "--staged-config",
            _V52,
            "--accounting-epoch-bundle",
            "v52-epoch",
        ]
    )

    module.resolve_launch(args, credentials_present=False)

    assert observed == {
        "bundle": Path("v52-epoch"),
        "profile_id": "multi_asset_growth_first_5000_evidence_bound_successor_v52",
    }


def _module() -> ModuleType:
    spec = spec_from_file_location("v51_v52_tui_transition", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load unified TUI launcher")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
