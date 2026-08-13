"""Unified-TUI identity checks for active v39 and staged six-asset v50."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/multi_asset_bidirectional_canary_tui.py")
_V39 = (
    "configs/multi_asset_bidirectional_hype_compression_range_retired_"
    "current_canary_v39.toml"
)
_V50 = "configs/multi_asset_growth_first_5000_six_asset_candidate_v50.toml"
_V51 = "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"


def test_monitor_stages_exact_v50_without_live_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cockpit must expose all six staged assets without arming them."""
    module = _module()
    monkeypatch.setattr(
        module, "load_required_accounting_epoch", lambda bundle, successor: None
    )
    args = module.build_parser().parse_args(
        ["--mode", "monitor", "--config", _V39, "--staged-config", _V50]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.config.profile_id.endswith("v39")
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id.endswith("v50")
    assert launch.staged_config.symbols == (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
    )
    assert len(launch.staged_config.executable_provider_symbols) == 7
    assert len(launch.staged_config.executable_provider_directions) == 12
    assert "--enabled" not in launch.tui_command
    assert "--i-accept-live-risk" not in launch.tui_command
    checkpoint = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint + 1] == _V50


def test_monitor_stages_profit_protected_v51_without_live_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cockpit must stage v51 exactly while remaining attach-only."""
    module = _module()
    monkeypatch.setattr(
        module, "load_required_accounting_epoch", lambda bundle, successor: None
    )
    args = module.build_parser().parse_args(
        ["--mode", "monitor", "--config", _V39, "--staged-config", _V51]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id.endswith("v51")
    assert len(launch.staged_config.symbols) == 6
    assert len(launch.staged_config.executable_provider_symbols) == 7
    assert len(launch.staged_config.executable_provider_directions) == 12
    assert "--enabled" not in launch.tui_command
    checkpoint = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint + 1] == _V51


def test_staged_v51_monitor_binds_its_successor_accounting_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 0/0 epoch belongs to staged v51 rather than active v39."""
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
            _V39,
            "--staged-config",
            _V51,
            "--accounting-epoch-bundle",
            "v51-epoch",
        ]
    )

    module.resolve_launch(args, credentials_present=False)

    assert observed == {
        "bundle": Path("v51-epoch"),
        "profile_id": "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51",
    }


def _module() -> ModuleType:
    spec = spec_from_file_location("v39_v50_tui_transition", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load unified TUI launcher")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
