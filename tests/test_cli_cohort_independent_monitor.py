"""An independently owned TUI remains outside the financial launcher boundary."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from hypervector.cli import build_parser
from hypervector.cli_cohort import cohort_command


def test_independent_monitor_selects_report_only_script() -> None:
    """The explicit option forwards configuration and authenticated TUI selection."""
    args = build_parser().parse_args([
        "cohort-tui", "--mode", "monitor", "--independent-monitor",
        "--config", "configs/example.toml", "--tui-bin", "/tmp/tui",
        "--tui-bin-sha256", "a" * 64,
    ])
    command = cohort_command(args)
    assert Path(command[1]).name == "cohort_independent_monitor.py"
    assert command[command.index("--config") + 1] == "configs/example.toml"
    assert command[command.index("--tui-bin") + 1] == "/tmp/tui"
    assert command[command.index("--tui-bin-sha256") + 1] == "a" * 64
    assert command[-2:] == ("--mode", "monitor")
    assert "--enabled" not in command and "--i-accept-live-risk" not in command


@pytest.mark.parametrize("mode", ["observe", "live"])
def test_independent_option_cannot_select_a_backend(mode: str) -> None:
    """The option cannot create an independent financial or shadow backend."""
    values = ["cohort-tui", "--mode", mode, "--independent-monitor"]
    if mode == "live":
        values += ["--enabled", "--i-accept-live-risk"]
    args = build_parser().parse_args(values)
    with pytest.raises(ValueError, match="independent monitor requires monitor mode"):
        cohort_command(args)


@pytest.mark.parametrize("independent", [False, True])
def test_process_entrypoint_loads_no_credentials_for_independent_monitor(
    monkeypatch: pytest.MonkeyPatch, independent: bool,
) -> None:
    """The real argv entrypoint loads dotenv only for the existing command path."""
    from hypervector import cli, cli_cohort

    loaded: list[bool] = []
    values = ["hypervector", "cohort-tui", "--mode", "monitor"]
    if independent:
        values.append("--independent-monitor")
    monkeypatch.setattr(cli.sys, "argv", values)
    monkeypatch.setattr(cli, "_load_dotenv_if_present", lambda: loaded.append(True))
    monkeypatch.setattr(cli_cohort.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0))
    assert cli.main() == 0
    assert loaded == ([] if independent else [True])


@pytest.mark.parametrize("flag", ["--enabled", "--i-accept-live-risk"])
def test_independent_monitor_rejects_execution_flags(flag: str) -> None:
    """Read-only monitoring never acquires an execution permission flag."""
    args = build_parser().parse_args([
        "cohort-tui", "--mode", "monitor", "--independent-monitor", flag,
    ])
    with pytest.raises(ValueError, match="cannot accept live authority"):
        cohort_command(args)
