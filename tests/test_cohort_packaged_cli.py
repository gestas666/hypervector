"""Cohort transport must remain installable and fail closed after TUI removal."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.cli import build_parser
from hypervector.cli_cohort import cohort_command


def test_cohort_live_uses_an_installed_module() -> None:
    """Execution may not rely on a checkout-relative scripts directory."""
    args = build_parser().parse_args(
        ["cohort", "live", "--enabled", "--i-accept-live-risk"]
    )
    command = cohort_command(args)
    assert command[1:3] == (
        "-m",
        "hypervector.operations.multi_asset_bidirectional_live",
    )


@pytest.mark.parametrize("flags", [[], ["--enabled"], ["--i-accept-live-risk"]])
def test_packaged_live_refuses_incomplete_authority(flags: list[str]) -> None:
    """Packaging cannot weaken the existing two-flag contract."""
    args = build_parser().parse_args(["cohort", "live", *flags])
    with pytest.raises(ValueError, match="both"):
        cohort_command(args)


def test_observer_has_no_live_authority_options() -> None:
    """The retained production observer must expose zero-submit capability."""
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["cohort", "observe", "--enabled"])
    assert error.value.code == 2


def test_observer_defaults_to_an_isolated_paper_root(tmp_path: Path) -> None:
    """A profile's live ledger cannot become the default observation destination."""
    from hypervector.commands.operations import operation_command

    args = build_parser().parse_args(
        ["--data-root", str(tmp_path), "cohort", "observe", "--config", "profile.toml"]
    )
    command = operation_command(args)
    assert command[command.index("--ledger-root") + 1] == str(tmp_path / "paper/cohort")


@pytest.mark.parametrize(
    ("action", "flags"),
    [
        ("live", ["--config", "profile.toml", "--enabled", "--i-accept-live-risk"]),
        ("observe", ["--config", "profile.toml"]),
        ("checkpoint", []),
        ("observer-checkpoint", []),
        ("observer-audit", ["--out", "audit.json"]),
        ("audit", ["--out", "audit.json", "--run-id", "run"]),
        (
            "audit-delta",
            ["--before", "a.json", "--after", "b.json", "--out", "delta.json"],
        ),
        ("research-import", []),
    ],
)
def test_packaged_operation_options_match_the_public_cli(
    action: str, flags: list[str]
) -> None:
    """Every retained backend option must be reachable through its workflow."""
    from importlib import import_module

    from hypervector.commands.operations import operation_command
    from hypervector.commands.registry import command_specs

    spec = next(
        spec
        for group, spec in command_specs()
        if group == "cohort" and spec["action"] == action
    )
    module = import_module(f"hypervector.operations.{spec['operation']}")
    parser_factory = getattr(module, "build_parser", None) or module._parser
    service_parser = parser_factory()
    declared = {flag for argument in spec["arguments"] for flag in argument["flags"]}
    service = {
        flag
        for option in service_parser._actions
        for flag in option.option_strings
        if flag not in {"-h", "--help"}
    }
    assert declared == service
    args = build_parser().parse_args(["cohort", action, *flags])
    transported = service_parser.parse_args(list(operation_command(args)[3:]))
    for argument in spec["arguments"]:
        dest = argument["options"]["dest"]
        if action == "observe" and dest == "ledger_root":
            assert transported.ledger_root == Path("data/paper/cohort")
        else:
            assert getattr(transported, dest) == getattr(args, dest)
