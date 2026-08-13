"""Unified-TUI identity tests for active v39 versus inactive v42."""

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
_V42 = "configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml"
_V42_PREFLIGHT = (
    "data/runtime/bidirectional_cohort/latest_growth_5000_v42_preflight.json"
)


def test_monitor_can_stage_v42_without_starting_or_replacing_v39() -> None:
    """A staged growth view remains attach-only and execution-incapable."""
    module = _module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "monitor",
            "--config",
            _V39,
            "--staged-config",
            _V42,
            "--growth-preflight",
            _V42_PREFLIGHT,
        ]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.config.profile_id.endswith("v39")
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id.endswith("v42")
    assert len(launch.staged_config.assets) == 3
    assert len(launch.staged_config.executable_provider_symbols) == 3
    assert len(launch.staged_config.executable_provider_directions) == 6
    assert "--enabled" not in launch.tui_command
    assert "--i-accept-live-risk" not in launch.tui_command
    preflight = launch.tui_command.index("--growth-preflight")
    assert launch.tui_command[preflight + 1] == _V42_PREFLIGHT


def test_future_v42_live_command_binds_backend_and_checkpoint_to_v42() -> None:
    """Explicit future arming cannot mix v42 with another runtime identity."""
    module = _module()
    args = module.build_parser().parse_args(
        ["--mode", "live", "--config", _V42, "--enabled", "--i-accept-live-risk"]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.backend_command is not None
    backend = launch.backend_command.index("--config")
    checkpoint = launch.checkpoint_command.index("--config")
    assert launch.backend_command[backend + 1] == _V42
    assert launch.checkpoint_command[checkpoint + 1] == _V42
    assert "--enabled" in launch.backend_command
    assert "--i-accept-live-risk" in launch.backend_command


def _module() -> ModuleType:
    spec = spec_from_file_location("v39_v42_tui_transition", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load unified TUI launcher")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
