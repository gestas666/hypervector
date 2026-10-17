"""Cohort transport must remain installable and fail closed after TUI removal."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.cli import build_parser
from hypervector.commands.common import CommandRefused
from hypervector.commands.operations import operation_argv, run_operation

_PROFILE = ["--config", "profile.toml"]


def test_live_start_uses_an_installed_module() -> None:
    """Execution may not rely on a checkout-relative scripts directory."""
    args = build_parser().parse_args(
        ["live", "start", *_PROFILE, "--enabled", "--i-accept-live-risk"]
    )
    command = operation_argv(args)
    assert command[1:3] == (
        "-m",
        "hypervector.operations.multi_asset_bidirectional_live",
    )


@pytest.mark.parametrize("flags", [[], ["--enabled"], ["--i-accept-live-risk"]])
def test_packaged_live_refuses_incomplete_authority(flags: list[str]) -> None:
    """Packaging cannot weaken the existing two-flag contract."""
    args = build_parser().parse_args(["live", "start", *_PROFILE, *flags])
    with pytest.raises(CommandRefused, match="both"):
        run_operation(args)


def test_observer_has_no_live_authority_options() -> None:
    """The retained production observer must expose zero-submit capability."""
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["paper", "observe", *_PROFILE, "--enabled"])
    assert error.value.code == 2


def test_observer_defaults_to_an_isolated_paper_root(tmp_path: Path) -> None:
    """A profile's live ledger cannot become the default observation destination."""
    args = build_parser().parse_args(
        ["--data-root", str(tmp_path), "paper", "observe", *_PROFILE]
    )
    command = operation_argv(args)
    assert command[command.index("--ledger-root") + 1] == str(tmp_path / "paper/cohort")
