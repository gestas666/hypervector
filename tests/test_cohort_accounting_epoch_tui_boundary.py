"""Unified TUI launcher tests for the recoverable v49 accounting epoch."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "multi_asset_bidirectional_canary_tui.py"
)
V49 = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")


def _load() -> ModuleType:
    spec = spec_from_file_location("accounting_epoch_tui_boundary", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _live_args(module: ModuleType, *, bundle: bool) -> object:
    values = [
        "--mode",
        "live",
        "--config",
        str(V49),
        "--enabled",
        "--i-accept-live-risk",
    ]
    if bundle:
        values.extend(["--accounting-epoch-bundle", "epoch-v49"])
    return module.build_parser().parse_args(values)


def test_v49_unified_live_launch_refuses_a_missing_epoch() -> None:
    """A profile with a required rollover cannot start without its evidence."""
    module = _load()

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        module.resolve_launch(
            _live_args(module, bundle=False), credentials_present=True
        )


def test_v49_unified_launch_binds_epoch_to_backend_and_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resolved epoch reaches both owned commands with the selected profile."""
    module = _load()
    epoch = CohortAccountingEpoch("growth_5000_v49", "a" * 64, 1)
    calls: list[tuple[Path, str]] = []

    def load(bundle: Path, config: object) -> CohortAccountingEpoch:
        calls.append((bundle, config.profile_id))
        return epoch

    monkeypatch.setattr(module, "load_required_accounting_epoch", load)

    launch = module.resolve_launch(
        _live_args(module, bundle=True), credentials_present=True
    )

    assert launch.accounting_epoch == epoch
    assert calls == [(Path("epoch-v49"), launch.config.profile_id)]
    assert launch.backend_command is not None
    assert launch.checkpoint_command is not None
    for command in (launch.backend_command, launch.checkpoint_command):
        index = command.index("--accounting-epoch-bundle")
        assert command[index + 1] == "epoch-v49"


def test_parser_exposes_the_epoch_as_an_explicit_operator_input() -> None:
    """Retain the exact operator-selected accounting bundle path."""
    module = _load()

    args = module.build_parser().parse_args(
        ["--accounting-epoch-bundle", "data/backups/epoch-v49"]
    )

    assert args.accounting_epoch_bundle == Path("data/backups/epoch-v49")


def test_recent_checkpoint_must_carry_the_exact_epoch() -> None:
    """Checkpoint freshness does not substitute for matching accounting identity."""
    module = _load()
    epoch = CohortAccountingEpoch("growth_5000_v49", "a" * 64, 1)
    unscoped = {"audit": {"portfolio_archive": {"schema_version": 1}}}

    with pytest.raises(ValueError, match="checkpoint accounting epoch differs"):
        module._require_checkpoint_accounting_epoch(unscoped, epoch)

    exact = {"audit": {"portfolio_archive": {"accounting_epoch": epoch.to_dict()}}}
    module._require_checkpoint_accounting_epoch(exact, epoch)
