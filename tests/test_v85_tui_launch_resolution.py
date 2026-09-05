"""Exact command-resolution acceptance for the V85 one-command TUI launch."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.cohort_accounting_rollover import (
    load_required_accounting_epoch,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_SCRIPT = Path("scripts/multi_asset_bidirectional_canary_tui.py")
_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_btc_tuned_retired_v85.toml"
)
_EPOCH = Path(
    "data/backups/bidirectional_cohort/accounting_epochs/"
    "v85_btc_tuned_retired_18306afa_20260903T2057Z"
)
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK")


def test_v85_requires_its_exact_accounting_epoch() -> None:
    """The display epoch cannot silently fall back to mixed history."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        load_required_accounting_epoch(None, config)


def test_v85_one_command_resolves_full_roster_and_observer() -> None:
    """The launch must bind seven assets, eight executions, and nine observers."""
    module = _load_module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--config",
            str(_CONFIG),
            "--accounting-epoch-bundle",
            str(_EPOCH),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.config.symbols == _SYMBOLS
    assert len(launch.config.providers) == 9
    assert len(launch.config.executable_provider_symbols) == 8
    assert len(launch.config.executable_provider_directions) == 8
    assert launch.accounting_epoch is not None
    assert (
        launch.accounting_epoch.profile_fingerprint == launch.config.profile_fingerprint
    )
    assert launch.dependency_command is not None
    assert launch.dependency_command[-3:] == (
        "scripts/index_hip3_breakout_shadow_observe.py",
        "--symbol",
        "xyz:SPCX",
    )
    assert launch.backend_command is not None
    assert _bound(launch.backend_command, "--config") == str(_CONFIG)
    assert _bound(launch.backend_command, "--accounting-epoch-bundle") == str(_EPOCH)
    assert launch.checkpoint_command is not None
    assert _bound(launch.checkpoint_command, "--config") == str(_CONFIG)
    assert _bound(launch.checkpoint_command, "--accounting-epoch-bundle") == str(_EPOCH)


def _bound(command: tuple[str, ...], flag: str) -> str:
    """Return the exact value following one required command flag."""
    return command[command.index(flag) + 1]


def _load_module() -> ModuleType:
    """Load the supervisor without invoking its process boundary."""
    spec = spec_from_file_location("v85_tui_launch_resolution", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
