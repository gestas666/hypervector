"""Unified-TUI identity checks for active v39 and staged v45."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

_SCRIPT = Path("scripts/multi_asset_bidirectional_canary_tui.py")
_V39 = (
    "configs/multi_asset_bidirectional_hype_compression_range_retired_"
    "current_canary_v39.toml"
)
_V45 = (
    "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml"
)
_PREFLIGHT = "data/logs/research/bidirectional_cohort/v45_final_flat_preflight.json"


def test_monitor_stages_v45_without_live_authority() -> None:
    """The read-only cockpit compares v39 and v45 without starting a backend."""
    module = _module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "monitor",
            "--config",
            _V39,
            "--staged-config",
            _V45,
            "--growth-preflight",
            _PREFLIGHT,
        ]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.config.profile_id.endswith("v39")
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id.endswith("v45")
    assert len(launch.staged_config.assets) == 3
    assert len(launch.staged_config.executable_provider_symbols) == 4
    assert len(launch.staged_config.executable_provider_directions) == 6
    assert "--enabled" not in launch.tui_command
    assert "--i-accept-live-risk" not in launch.tui_command
    option = launch.tui_command.index("--growth-preflight")
    assert launch.tui_command[option + 1] == _PREFLIGHT
    checkpoint = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint + 1] == _V45


def test_future_v45_live_binds_backend_and_checkpoint_to_one_profile() -> None:
    """Explicit future arming cannot mix v45 with another runtime identity."""
    module = _module()
    args = module.build_parser().parse_args(
        ["--mode", "live", "--config", _V45, "--enabled", "--i-accept-live-risk"]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.backend_command is not None
    backend = launch.backend_command.index("--config")
    checkpoint = launch.checkpoint_command.index("--config")
    assert launch.backend_command[backend + 1] == _V45
    assert launch.checkpoint_command[checkpoint + 1] == _V45


def _module() -> ModuleType:
    spec = spec_from_file_location("v39_v45_tui_transition", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load unified TUI launcher")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
