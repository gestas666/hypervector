"""Exact command-resolution acceptance for the V86 one-command TUI launch."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

_SCRIPT = Path("scripts/multi_asset_bidirectional_canary_tui.py")
_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)
_EPOCH = Path(
    "data/backups/bidirectional_cohort/accounting_epochs/"
    "v86_failed_routes_retired_f454101e_PENDING"
)
_FINGERPRINT = "f454101eadaef46fd026c1a901bb7873bad61d7e7183a4c2e342e477e4e38733"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK")


def test_v86_one_command_resolves_full_roster_and_six_executions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The launch must bind seven assets, six executions, and nine observers."""
    module = _load_module()
    epoch = CohortAccountingEpoch("v86-test", _FINGERPRINT, 1_788_529_600_000)
    monkeypatch.setattr(module, "load_required_accounting_epoch", lambda *_: epoch)
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
    assert len(launch.config.executable_provider_directions) == 6
    assert launch.accounting_epoch == epoch
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
    spec = spec_from_file_location("v86_tui_launch_resolution", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
