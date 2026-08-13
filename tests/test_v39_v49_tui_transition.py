"""Unified-TUI identity checks for active v39 and staged v49."""

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
_V49 = "configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml"
_PREFLIGHT = "data/logs/research/bidirectional_cohort/v49_final_flat_preflight.json"


def test_monitor_stages_v49_without_live_authority() -> None:
    """The cockpit can compare v39 and repaired v49 without a backend start."""
    module = _module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "monitor",
            "--config",
            _V39,
            "--staged-config",
            _V49,
            "--growth-preflight",
            _PREFLIGHT,
        ]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.config.profile_id.endswith("v39")
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id.endswith("v49")
    assert len(launch.staged_config.assets) == 4
    assert len(launch.staged_config.executable_provider_symbols) == 5
    assert len(launch.staged_config.executable_provider_directions) == 8
    assert "--enabled" not in launch.tui_command
    assert "--i-accept-live-risk" not in launch.tui_command
    option = launch.tui_command.index("--growth-preflight")
    assert launch.tui_command[option + 1] == _PREFLIGHT
    checkpoint = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint + 1] == _V49


def _module() -> ModuleType:
    spec = spec_from_file_location("v39_v49_tui_transition", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load unified TUI launcher")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
