"""Generated contracts for the unified CLI surface: parse, help, data root, exec, env."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from cli_spec_fixtures import command_argv
from hypervector.cli import load_command_environment, main
from hypervector.commands import operations
from hypervector.commands.common import CommandRefused
from hypervector.commands.registry import (
    ACTIONS,
    CLI_COMMANDS,
    LEGACY_ALIASES,
    LEGACY_GROUPS,
    OPERATION_HANDLER,
    RETIRED,
    argument_dest,
    build_parser,
    command_specs,
    iter_arguments,
    spec_for,
)

HEAVY_MODULES = (
    "pandas",
    "numpy",
    "vectorbt",
    "nautilus_trader",
    "duckdb",
    "hyperliquid",
    "talib",
    "optuna",
    "lightgbm",
    "plotly",
    "requests",
)
LIVE_BACKEND = "hypervector.operations.multi_asset_bidirectional_live"
OLD_WORDS = {key for key in [*LEGACY_ALIASES, *RETIRED] if " " not in key} | set(
    LEGACY_GROUPS
)


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return next(
        action.choices
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )


def _listed_names(help_text: str) -> set[str]:
    """First-column names of the epilog listings (groups or actions)."""
    return set(re.findall(r"^  ([a-z][a-z0-9-]*)\s{2,}\S", help_text, flags=re.M))


@pytest.mark.parametrize("command", CLI_COMMANDS)
def test_every_spec_parses_with_minimal_arguments(command: str) -> None:
    """Each command parses from its required options and dispatches to its handler."""
    args = build_parser().parse_args(command_argv(command))
    spec = spec_for(command)
    expected = spec.get("handler", OPERATION_HANDLER)
    assert args.command == command
    assert (args.group, args.action) == tuple(command.split())
    assert args.func.target == expected


@pytest.mark.parametrize("command", CLI_COMMANDS)
def test_every_command_help_renders(command: str, capsys) -> None:
    """Help formats for every command (no broken %-placeholders) and exits 0."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([*command.split(), "--help"])
    assert exc.value.code == 0
    assert "usage: hypervector " + command in capsys.readouterr().out


def test_root_and_group_help_list_only_canonical_names() -> None:
    """Old names are rewritten before parsing, so help never shows them."""
    parser = build_parser()
    root_help = parser.format_help()
    assert _listed_names(root_help) - {"status"} == set(ACTIONS)
    for group, group_parser in _subparsers(parser).items():
        listed = _listed_names(group_parser.format_help())
        assert listed == set(ACTIONS[group]), group
    assert not OLD_WORDS & set(_subparsers(parser))


@pytest.mark.parametrize(
    "argv", [["backtst"], ["live", "bogus"], ["paper", "observer-audit-x"]]
)
def test_invalid_choice_lists_only_canonical_names(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(argv)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    listed = err.split("choose from", 1)[1].split(")", 1)[0]
    choices = {name.strip(" '") for name in listed.split(",")}
    expected = set(ACTIONS) if len(argv) == 1 else set(ACTIONS[argv[0]])
    assert choices == expected


def _import_guard(argv: list[str], tmp_path: Path) -> None:
    program = (
        "import sys\n"
        "from hypervector.cli import main\n"
        "try:\n"
        f"    main({argv!r})\n"
        "except SystemExit:\n"
        "    pass\n"
        f"heavy = sorted(set({HEAVY_MODULES!r}) & set(sys.modules))\n"
        "assert not heavy, heavy\n"
    )
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=30,
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.mark.parametrize(
    "argv",
    [["--help"], *[[group, "--help"] for group in ACTIONS], ["live", "check"]],
)
def test_discovery_does_not_import_engines(argv: list[str], tmp_path: Path) -> None:
    """Help, group help and readiness work without heavy engine imports."""
    _import_guard(argv, tmp_path)


def test_status_does_not_import_engines(tmp_path: Path) -> None:
    _import_guard(["--data-root", str(tmp_path / "data"), "system", "status"], tmp_path)
    assert not (tmp_path / "data").exists()


def _honored_with_data_defaults() -> list[str]:
    return [
        f"{group} {action}"
        for group, action, spec in command_specs()
        if spec["data_root"] == "honored"
        and any(argument.get("data_default") for argument in iter_arguments(spec))
    ]


@pytest.mark.parametrize("command", _honored_with_data_defaults())
def test_data_defaults_follow_the_data_root(command: str, tmp_path: Path) -> None:
    """Every data-relative default resolves under an explicit --data-root."""
    args = build_parser().parse_args(
        ["--data-root", str(tmp_path), *command_argv(command)]
    )
    for argument in iter_arguments(spec_for(command)):
        relative = argument.get("data_default")
        if relative:
            value = Path(getattr(args, argument_dest(argument)))
            assert value == tmp_path / relative


@pytest.mark.parametrize(
    "command",
    [f"{g} {a}" for g, a, spec in command_specs() if spec["data_root"] == "refused"],
)
def test_refused_specs_reject_a_foreign_data_root(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Paths fixed by the profile or launchd cannot be redirected by --data-root."""
    build_parser().parse_args(command_argv(command))
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(
            ["--data-root", str(tmp_path), *command_argv(command)]
        )
    assert exc.value.code == 2
    assert "--data-root is not supported" in capsys.readouterr().err


def test_regime_options_before_an_action_are_not_reinterpreted() -> None:
    """'regime --symbol ETH eval' used to run the classifier; now it is an error."""
    with pytest.raises(SystemExit) as exc:
        main(["regime", "--symbol", "ETH", "eval"])
    assert exc.value.code == 2


@pytest.fixture
def exec_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        operations, "_exec", lambda path, argv: calls.append((path, argv))
    )
    monkeypatch.setattr(
        "hypervector.live.multi_asset_live_config.load_multi_asset_live_config",
        lambda path, mode: {"path": path, "mode": mode},
    )
    return calls


@pytest.mark.parametrize("flags", [[], ["--enabled"], ["--i-accept-live-risk"]])
def test_live_start_without_both_flags_never_execs(
    flags: list[str], exec_calls: list[tuple[str, list[str]]], capsys
) -> None:
    assert main(["live", "start", "--config", "profile.toml", *flags]) == 2
    assert exec_calls == []
    report = json.loads(capsys.readouterr().err)
    assert report["command"] == "live start"
    assert "both --enabled and --i-accept-live-risk" in report["error"]


def test_live_start_with_both_flags_replaces_the_process(
    exec_calls: list[tuple[str, list[str]]],
) -> None:
    argv = ["live", "start", "--config", "p.toml", "--enabled", "--i-accept-live-risk"]
    assert main(argv) == 0
    [(path, command)] = exec_calls
    assert path == sys.executable
    assert command[:3] == [sys.executable, "-m", LIVE_BACKEND]
    assert command[command.index("--config") + 1] == "p.toml"
    assert {"--enabled", "--i-accept-live-risk"} <= set(command)


def test_live_start_preflight_refusal_never_execs(
    exec_calls: list[tuple[str, list[str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: Path, mode: str) -> None:
        raise ValueError("profile is not loadable")

    monkeypatch.setattr(
        "hypervector.live.multi_asset_live_config.load_multi_asset_live_config", broken
    )
    argv = ["live", "start", "--config", "p.toml", "--enabled", "--i-accept-live-risk"]
    assert main(argv) == 2
    assert exec_calls == []


def test_current_run_audit_without_a_run_id_is_refused(
    exec_calls: list[tuple[str, list[str]]], capsys
) -> None:
    assert main(["live", "audit", "--out", "audit.json"]) == 2
    assert exec_calls == []
    assert "--history-scope all-time" in capsys.readouterr().err


def test_unpatched_exec_is_refused_in_tests() -> None:
    """The conftest guard makes any operation exec fail loudly."""
    args = build_parser().parse_args(["paper", "observe", "--config", "p.toml"])
    with pytest.raises(AssertionError, match="exec in tests"):
        operations.run_operation(args)


def _environment_calls(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> list[object]:
    import hypervector.runtime_env as runtime_env

    calls: list[object] = []
    monkeypatch.setattr(
        runtime_env, "load_dotenv_if_present", lambda **_kwargs: calls.append("full")
    )
    monkeypatch.setattr(
        runtime_env,
        "load_selected_env_if_present",
        lambda keys, **_kwargs: calls.append(tuple(sorted(keys))),
    )
    load_command_environment(build_parser().parse_args(argv))
    return calls


@pytest.mark.parametrize("command", CLI_COMMANDS)
def test_environment_loading_follows_the_spec(
    command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full dotenv (signing key) loads only for armed live execution commands."""
    declared = spec_for(command)["environment"]
    unarmed = _environment_calls(monkeypatch, command_argv(command))
    assert "full" not in unarmed
    if "oxa" in declared:
        assert ("OXA_API_KEY",) in unarmed
    if "models" in declared:
        assert ("HYPERVECTOR_METALABEL_ROOT",) in unarmed
    if not declared:
        assert unarmed == []
    if "live-credentials" in declared:
        armed = command_argv(command) + ["--enabled", "--i-accept-live-risk"]
        assert _environment_calls(monkeypatch, armed) == ["full"]


def test_only_live_execution_specs_declare_credentials() -> None:
    declared = {
        f"{g} {a}"
        for g, a, spec in command_specs()
        if "live-credentials" in spec["environment"]
    }
    assert declared == {"live start", "live run"}


def test_error_boundary_prints_json_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def broken(_args: argparse.Namespace) -> int:
        raise OSError("disk unavailable")

    monkeypatch.setattr("hypervector.commands.status.cmd_infra_init", broken)
    assert main(["--data-root", str(tmp_path), "system", "init"]) == 1
    err = capsys.readouterr().err
    assert json.loads(err) == {
        "ok": False,
        "command": "system init",
        "error_type": "OSError",
        "error": "disk unavailable",
    }
    assert "Traceback" not in err


@pytest.mark.parametrize(
    ("raised", "code"), [(CommandRefused("no"), 2), (KeyboardInterrupt(), 130)]
)
def test_error_boundary_exit_codes(
    raised: BaseException, code: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def broken(_args: argparse.Namespace) -> int:
        raise raised

    monkeypatch.setattr("hypervector.commands.status.cmd_infra_init", broken)
    assert main(["--data-root", str(tmp_path), "system", "init"]) == code


def test_debug_mode_reraises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def broken(_args: argparse.Namespace) -> int:
        raise RuntimeError("engine failed")

    monkeypatch.setattr("hypervector.commands.status.cmd_infra_init", broken)
    monkeypatch.setenv("HYPERVECTOR_DEBUG", "1")
    with pytest.raises(RuntimeError, match="engine failed"):
        main(["--data-root", str(tmp_path), "system", "init"])


def test_unknown_fee_model_and_short_lookback_exit_two() -> None:
    parser = build_parser()
    for argv in (
        ["backtest", "run", "--fee-model", "hl_platinum"],
        ["data", "history", "--lookback-days", "10"],
    ):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(argv)
        assert exc.value.code == 2


def test_fee_aliases_and_hybrid_sampler_normalize(capsys) -> None:
    parser = build_parser()
    assert parser.parse_args(["backtest", "run", "--fee-model", "vip1"]).fee_model == (
        "hl_vip1_taker"
    )
    assert parser.parse_args(["tune", "strategy", "--sampler", "hybrid"]).sampler == (
        "optuna"
    )
    assert "now --sampler optuna" in capsys.readouterr().err
