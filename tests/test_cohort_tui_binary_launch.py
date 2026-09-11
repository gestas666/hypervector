"""Prebuilt cohort TUI propagation and child-start boundaries without execution."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest

from hypervector.cli_cohort import cohort_command, register_cohort_commands
from hypervector.live.cohort_tui_commands import launch_checkpoint_command
import multi_asset_bidirectional_canary_tui as supervisor

CONFIG = "configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml"


@pytest.fixture
def executable(tmp_path: Path) -> tuple[Path, str]:
    """Create inert executable bytes without spawning anything."""
    path = tmp_path / "prebuilt tui"
    path.write_bytes(b"inert qualified TUI fixture\n")
    path.chmod(0o700)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _arguments(executable: tuple[Path, str], mode: str) -> list[str]:
    path, digest = executable
    return [
        "--mode",
        mode,
        "--config",
        CONFIG,
        "--tui-bin",
        str(path),
        "--tui-bin-sha256",
        digest,
        *(["--enabled", "--i-accept-live-risk"] if mode == "live" else []),
    ]


@pytest.mark.parametrize("mode", ["observe", "monitor", "live"])
def test_cli_forwards_exact_explicit_binary_selection(
    executable: tuple[Path, str], mode: str
) -> None:
    """The outer CLI retains both identity arguments without executing its command."""
    parser = argparse.ArgumentParser()
    register_cohort_commands(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(["cohort-tui", *_arguments(executable, mode)])
    command = cohort_command(args)
    assert command[command.index("--tui-bin") + 1] == str(executable[0])
    assert command[command.index("--tui-bin-sha256") + 1] == executable[1]
    assert ("--enabled" in command) is (mode == "live")


@pytest.mark.parametrize("mode", ["observe", "monitor", "live"])
def test_prebuilt_command_keeps_all_existing_data_arguments(
    executable: tuple[Path, str], mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the foreground executable prefix changes; command construction spawns nothing."""
    monkeypatch.setattr(
        supervisor.subprocess, "Popen", Mock(side_effect=AssertionError)
    )
    monkeypatch.setattr(supervisor.subprocess, "run", Mock(side_effect=AssertionError))
    parser = supervisor.build_parser()
    selected = supervisor.resolve_launch(
        parser.parse_args(_arguments(executable, mode)), credentials_present=True
    )
    old_args = ["--mode", mode, "--config", CONFIG]
    if mode == "live":
        old_args += ["--enabled", "--i-accept-live-risk"]
    previous = supervisor.resolve_launch(
        parser.parse_args(old_args), credentials_present=True
    )
    separator = previous.tui_command.index("--")
    assert selected.tui_command == (
        str(executable[0]),
        *previous.tui_command[separator + 1 :],
    )
    assert selected.backend_command == previous.backend_command
    assert selected.checkpoint_command == previous.checkpoint_command
    assert selected.dependency_command == previous.dependency_command
    assert selected.config.profile_fingerprint == previous.config.profile_fingerprint
    assert selected.tui_binary.sha256 == executable[1]


@pytest.mark.parametrize("mode", ["observe", "monitor", "live"])
def test_drift_is_refused_before_any_supervisor_child(
    executable: tuple[Path, str], mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No backend, report writer or dependency starts after resolved binary drift."""
    launch = supervisor.resolve_launch(
        supervisor.build_parser().parse_args(_arguments(executable, mode)),
        credentials_present=True,
    )
    executable[0].write_bytes(b"unexpected replacement")
    children = [Mock(side_effect=AssertionError) for _ in range(3)]
    for name, child in zip(
        ["_run_live_supervisor", "_run_monitor", "_start_owned_dependency"],
        children,
        strict=True,
    ):
        monkeypatch.setattr(supervisor, name, child)
    with pytest.raises(RuntimeError, match="SHA256 differs"):
        supervisor.run_supervisor(launch)
    assert all(child.call_count == 0 for child in children)


def test_drift_is_rechecked_immediately_before_foreground_invocation(
    executable: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed executable cannot run after the backend's readiness wait."""
    launch = supervisor.resolve_launch(
        supervisor.build_parser().parse_args(_arguments(executable, "live")),
        credentials_present=True,
    )
    executable[0].write_bytes(b"replacement during backend startup")
    invocation = Mock(side_effect=AssertionError)
    monkeypatch.setattr(supervisor.subprocess, "run", invocation)
    with pytest.raises(RuntimeError, match="SHA256 differs"):
        supervisor._run_tui(launch)
    invocation.assert_not_called()


def test_foreground_invocation_uses_exact_verified_command(
    executable: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The subprocess boundary receives the retained executable and propagates its status."""
    launch = supervisor.resolve_launch(
        supervisor.build_parser().parse_args(_arguments(executable, "monitor")),
        credentials_present=False,
    )
    result = Mock(returncode=7)
    invocation = Mock(return_value=result)
    monkeypatch.setattr(supervisor.subprocess, "run", invocation)
    assert supervisor._run_tui(launch) == 7
    invocation.assert_called_once_with(launch.tui_command, check=False)


@pytest.mark.parametrize("mode", ["observe", "live"])
def test_binary_drift_during_readiness_cleans_up_owned_children(
    executable: tuple[Path, str], mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed foreground verification still reaches both existing cleanup paths."""
    launch = supervisor.resolve_launch(
        supervisor.build_parser().parse_args(_arguments(executable, mode)),
        credentials_present=True,
    )
    launch = replace(
        launch, config=replace(launch.config, stop_file=executable[0].parent / "STOP")
    )
    backend, checkpoint = Mock(), Mock()
    stop_backend, stop_checkpoint = Mock(), Mock(return_value=None)
    invocation = Mock(side_effect=AssertionError)
    monkeypatch.setattr(
        supervisor, "_BACKEND_LOG", executable[0].parent / "backend.log"
    )
    monkeypatch.setattr(supervisor, "capture_ledger_start", Mock(return_value=object()))
    monkeypatch.setattr(supervisor.subprocess, "Popen", Mock(return_value=backend))
    monkeypatch.setattr(supervisor.subprocess, "run", invocation)
    monkeypatch.setattr(
        supervisor, "_start_checkpoint_monitor", Mock(return_value=checkpoint)
    )
    monkeypatch.setattr(supervisor, "_stop_checkpoint_monitor", stop_checkpoint)
    monkeypatch.setattr(supervisor, "_stop_owned_backend", stop_backend)
    monkeypatch.setattr(
        supervisor, "_bind_run_to_active_backend", Mock(return_value=("report",))
    )
    monkeypatch.setattr(
        supervisor,
        "_wait_for_backend",
        Mock(
            side_effect=lambda *_args: executable[0].write_bytes(
                b"drift during readiness"
            )
        ),
    )
    with pytest.raises(RuntimeError, match="SHA256 differs"):
        supervisor.run_supervisor(launch)
    stop_checkpoint.assert_called_once_with(checkpoint)
    stop_backend.assert_called_once_with(backend, launch.config)
    invocation.assert_not_called()


def test_checkpoint_selection_refuses_unknown_mode() -> None:
    """An invalid lifecycle mode cannot become an observer through a default branch."""
    args = supervisor.build_parser().parse_args(["--config", CONFIG])
    config = supervisor.resolve_launch(args, credentials_present=False).config
    args.mode = "invalid"
    with pytest.raises(supervisor.MultiAssetLiveConfigError, match="unsupported TUI mode"):
        launch_checkpoint_command(args, config, None)
