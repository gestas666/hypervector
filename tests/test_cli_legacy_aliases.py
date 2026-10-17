"""Old command names and flag spellings keep working without appearing in help."""

from __future__ import annotations

import pytest

from cli_spec_fixtures import minimal_argv, sample_value
from hypervector.cli import main
from hypervector.commands.registry import (
    LEGACY_ALIASES,
    LEGACY_GROUPS,
    RETIRED,
    build_parser,
    command_specs,
    iter_arguments,
    normalize_argv,
    spec_for,
)


def _parsed(argv: list[str]) -> dict[str, object]:
    return vars(build_parser().parse_args(argv))


@pytest.mark.parametrize("old", sorted(LEGACY_ALIASES))
def test_legacy_command_parses_like_its_replacement(old: str) -> None:
    legacy = LEGACY_ALIASES[old]
    command = " ".join(legacy.words)
    rest = minimal_argv(spec_for(command), skip=legacy.insert[::2])
    assert _parsed([*old.split(), *rest]) == _parsed(
        [*legacy.words, *legacy.insert, *rest]
    )


@pytest.mark.parametrize("old", sorted(LEGACY_ALIASES))
@pytest.mark.parametrize("form", ["separate", "joined"])
def test_data_root_before_a_legacy_name_is_preserved(old: str, form: str) -> None:
    legacy = LEGACY_ALIASES[old]
    spec = spec_for(" ".join(legacy.words))
    rest = minimal_argv(spec, skip=legacy.insert[::2])
    name = "data" if spec["data_root"] == "refused" else "isolated"
    root = ["--data-root", name] if form == "separate" else [f"--data-root={name}"]
    args = build_parser().parse_args([*root, *old.split(), *rest])
    assert args.data_root == name
    assert args.command == " ".join(legacy.words)


@pytest.mark.parametrize("old", sorted(RETIRED))
def test_retired_names_exit_two_with_their_message(
    old: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(old.split())
    assert exc.value.code == 2
    assert RETIRED[old] in capsys.readouterr().err


@pytest.mark.parametrize("group", sorted(LEGACY_GROUPS))
def test_unknown_action_in_a_legacy_group_names_the_new_groups(
    group: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main([group, "no-such-action"])
    assert exc.value.code == 2
    assert RETIRED[group] in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "dest", "value"),
    [
        (["paper", "run", "--export", "cohort-tui"], "export", "cohort-tui"),
        (["backtest", "run", "--strategy", "sweep-up"], "strategy", "sweep-up"),
        (["nautilus", "check", "--export", "research"], "export", "research"),
        (["model", "train", "--export", "phase2-run"], "export", "phase2-run"),
    ],
)
def test_option_values_equal_to_old_words_are_untouched(
    argv: list[str], dest: str, value: str
) -> None:
    assert normalize_argv(argv) == argv
    assert _parsed(argv)[dest] == value


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (["backtest", "--symbol", "ETH"], ["backtest", "run", "--symbol", "ETH"]),
        (["regime", "--symbol", "ETH"], ["regime", "classify", "--symbol", "ETH"]),
        (
            ["export", "--track", "uptrend"],
            ["export", "create", "--track", "uptrend"],
        ),
    ],
)
def test_bare_group_options_select_the_default_action(
    old: list[str], new: list[str]
) -> None:
    assert _parsed(old) == _parsed(new)


@pytest.mark.parametrize("group", ["backtest", "export", "regime"])
def test_bare_default_action_groups_print_usage(group: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([group])
    assert exc.value.code == 2


def _legacy_flags() -> list[tuple[str, str, str, str]]:
    cases = []
    for group, action, spec in command_specs():
        for argument in iter_arguments(spec):
            for flag in argument.get("legacy_flags", []):
                value = (
                    ""
                    if argument["options"].get("action") == "store_true"
                    else sample_value(argument)
                )
                cases.append((f"{group} {action}", argument["flags"][0], flag, value))
    return cases


@pytest.mark.parametrize(("command", "canonical", "legacy", "value"), _legacy_flags())
def test_legacy_flag_spellings_parse_to_the_canonical_option(
    command: str, canonical: str, legacy: str, value: str
) -> None:
    rest = minimal_argv(spec_for(command), skip=[canonical])
    tail = [value] if value else []
    assert _parsed([*command.split(), *rest, legacy, *tail]) == _parsed(
        [*command.split(), *rest, canonical, *tail]
    )


def test_sweep_export_flag_is_a_hidden_no_op() -> None:
    base = ["backtest", "sweep", "--track", "uptrend"]
    assert _parsed([*base, "--export"]) == _parsed(base)
    assert _parsed(base)["no_export"] is False


def test_legacy_flags_are_hidden_from_help() -> None:
    help_text = build_parser()._subparsers._group_actions[0].choices["paper"]
    paper_help = help_text._subparsers._group_actions[0].choices["run"].format_help()
    assert "--poll-interval" not in paper_help
    assert "--path" not in paper_help
    assert "--interval-seconds" in paper_help
