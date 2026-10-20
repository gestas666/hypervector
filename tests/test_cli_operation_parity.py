"""Operation specs must transport exactly the packaged service's own options."""

from __future__ import annotations

import argparse
from importlib import import_module
from pathlib import Path

import pytest

from cli_spec_fixtures import command_argv
from hypervector.commands.operations import operation_argv
from hypervector.commands.registry import (
    argument_dest,
    build_parser,
    command_specs,
    iter_arguments,
    spec_for,
)

OPERATIONS = [
    f"{g} {a}" for g, a, spec in command_specs() if spec["kind"] == "operation"
]


def _service_parser(command: str) -> argparse.ArgumentParser:
    module = import_module(spec_for(command)["operation"])
    factory = getattr(module, "build_parser", None) or module._parser
    return factory()


def _transported_flags(command: str) -> set[str]:
    flags: set[str] = set()
    for argument in iter_arguments(spec_for(command)):
        flag = argument.get("transport", argument["flags"][0])
        if flag is False or argument.get("hidden"):
            continue
        flags.add(flag)
        if argument["options"].get("action") == "boolean_optional":
            flags.add("--no-" + flag[2:])
    return flags


def _module_dest(argument: dict) -> str:
    flag = argument.get("transport", argument["flags"][0])
    return str(flag).lstrip("-").replace("-", "_")


@pytest.mark.parametrize("command", OPERATIONS)
def test_transport_flags_equal_the_service_flags(command: str) -> None:
    service = {
        flag
        for action in _service_parser(command)._actions
        for flag in action.option_strings
        if flag not in {"-h", "--help"}
    }
    assert _transported_flags(command) == service


@pytest.mark.parametrize("command", OPERATIONS)
def test_transport_round_trips_every_value(command: str, tmp_path: Path) -> None:
    root = (
        []
        if spec_for(command)["data_root"] == "refused"
        else ["--data-root", str(tmp_path)]
    )
    args = build_parser().parse_args([*root, *command_argv(command)])
    argv = operation_argv(args)
    assert argv[2] == spec_for(command)["operation"]
    transported = _service_parser(command).parse_args(list(argv[3:]))
    for argument in iter_arguments(spec_for(command)):
        if argument.get("hidden") or argument.get("transport") is False:
            continue
        value = getattr(args, argument_dest(argument))
        assert getattr(transported, _module_dest(argument)) == value, argument["flags"]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [([], True), (["--current-run-only"], True), (["--no-current-run-only"], False)],
)
def test_checkpoint_current_run_scope_is_always_explicit(
    flags: list[str], expected: bool
) -> None:
    args = build_parser().parse_args([*command_argv("live checkpoint"), *flags])
    argv = operation_argv(args)
    assert ("--current-run-only" in argv) is expected
    assert ("--no-current-run-only" in argv) is not expected
    transported = _service_parser("live checkpoint").parse_args(list(argv[3:]))
    assert transported.current_run_only is expected


def test_installed_checkpoint_plist_arguments_still_parse() -> None:
    """The launchd checkpoint argv (pinned script) stays valid for the module parser."""
    plist = [
        "--ledger-root",
        "data/live/bidirectional_cohort",
        "--out",
        "data/runtime/bidirectional_cohort/latest_checkpoint.json",
        "--config",
        "tests/fixtures/cohort_chain/profile_b.toml",
        "--research-database",
        "data/research/market.duckdb",
        "--research-sync-interval-seconds",
        "120",
        "--venue-portfolio",
        "--current-run-only",
        "--disable-asymmetric-forward-observer",
        "--follow-latest-run",
    ]
    parsed = _service_parser("live checkpoint").parse_args(plist)
    assert parsed.current_run_only is True
    assert parsed.disable_asymmetric_forward_observer is True


def test_unset_optional_values_are_not_transported() -> None:
    args = build_parser().parse_args(command_argv("live checkpoint"))
    argv = operation_argv(args)
    assert "--asymmetric-forward-journal" not in argv
    assert "--research-database" not in argv
    assert "--enabled" not in argv
