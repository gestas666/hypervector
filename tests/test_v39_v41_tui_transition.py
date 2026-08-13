"""Command-level TUI acceptance for the v39-to-v41 transition."""

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
_V41 = (
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)
_PREFLIGHT = (
    "data/runtime/bidirectional_cohort/growth_5000_v41_preflight_20260811T1718Z.json"
)


def test_monitor_can_compare_active_v39_to_staged_v41_without_authority() -> None:
    """The staged growth view cannot start or replace the live backend."""
    module = _module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "monitor",
            "--config",
            _V39,
            "--staged-config",
            _V41,
            "--growth-preflight",
            _PREFLIGHT,
        ]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.config.profile_id.endswith("v39")
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id.endswith("v41")
    assert len(launch.staged_config.assets) == 8
    assert len(launch.staged_config.executable_provider_symbols) == 14
    assert len(launch.staged_config.executable_provider_directions) == 28
    assert "--enabled" not in launch.tui_command
    assert "--i-accept-live-risk" not in launch.tui_command
    option = launch.tui_command.index("--growth-preflight")
    assert launch.tui_command[option + 1] == _PREFLIGHT
    checkpoint = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint + 1] == _V41


def test_future_v41_live_command_binds_backend_and_checkpoint_to_v41() -> None:
    """Explicit arming cannot mix a different backend or checkpoint profile."""
    module = _module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--config",
            _V41,
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.backend_command is not None
    backend = launch.backend_command.index("--config")
    checkpoint = launch.checkpoint_command.index("--config")
    assert launch.backend_command[backend + 1] == _V41
    assert launch.checkpoint_command[checkpoint + 1] == _V41
    assert "--enabled" in launch.backend_command
    assert "--i-accept-live-risk" in launch.backend_command


def _module() -> ModuleType:
    spec = spec_from_file_location("v39_v41_tui_transition", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load unified TUI launcher")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
