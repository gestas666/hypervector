"""Only the independently owned reporter and TUI participate in shutdown."""

from dataclasses import replace
from importlib import import_module
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from hypervector.live.cohort_monitor_identity import MonitorIdentity
from hypervector.live.process_signal_stop import ProcessSignalStop
from test_cohort_independent_checkpoint import CONFIG, _source
from test_multi_asset_bidirectional_canary_tui_script import _load_module


class Child:
    """Deterministic child process with observable PID-local termination."""

    def __init__(self, pid: int, results: list[int | None]) -> None:
        self.pid = pid
        self.results = results
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        """Advance only the declared child status observations."""
        self.returncode = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return self.returncode

    def terminate(self) -> None:
        """Record termination of this one child."""
        self.terminated = True

    def wait(self, timeout: float) -> int:
        """Reap the simulated child immediately."""
        self.returncode = 0
        return 0


@pytest.mark.parametrize("case", ["quit", "tui_failure", "worker_failure", "startup_timeout", "signal"])
def test_monitor_stops_only_its_owned_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    """No branch invokes a financial backend or cleans up an external session."""
    module = import_module("hypervector.live.cohort_independent_monitor")
    launcher = _load_module()
    launch = launcher.resolve_launch(
        launcher.build_parser().parse_args(["--mode", "monitor", "--config", str(CONFIG)]),
        credentials_present=False,
    )
    source = _source()
    identity = MonitorIdentity("active", launch.config.profile_id, launch.config.profile_fingerprint)
    monkeypatch.setattr(module, "active_ledger_identity", lambda _config: identity)
    monkeypatch.setattr(module, "fresh_checkpoint_document", lambda *_a, **_k: source)
    worker = Child(50001, [2] if case == "worker_failure" else [None])
    tui = Child(50002, [None] if case in {"worker_failure", "signal"} else [7] if case == "tui_failure" else [0])
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
    stopped: list[int] = []

    def spawn(command: tuple[str, ...], **options: object) -> Child:
        calls.append((command, options))
        return worker if len(calls) == 1 else tui

    def ready(*_args: object, **_kwargs: object) -> None:
        if case == "startup_timeout":
            raise RuntimeError("checkpoint not ready")

    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    monkeypatch.setattr(module, "wait_for_checkpoint_readiness", ready)
    monkeypatch.setattr(module, "stop_owned_dependency", lambda child: stopped.append(child.pid))
    stop = ProcessSignalStop(requested=case == "signal")
    if case in {"worker_failure", "startup_timeout"}:
        with pytest.raises(RuntimeError):
            module.run_independent_monitor(launch, runtime_root=tmp_path, stop=stop)
    else:
        expected = 130 if case == "signal" else 7 if case == "tui_failure" else 0
        assert module.run_independent_monitor(launch, runtime_root=tmp_path, stop=stop) == expected
    assert stopped == [50001]
    assert len(calls) == (1 if case == "startup_timeout" else 2)
    assert calls[0][1]["start_new_session"] is True
    assert calls[0][1]["stdin"] == subprocess.DEVNULL
    assert all("scripts/multi_asset_bidirectional_live.py" not in " ".join(command) for command, _ in calls)
    worker_command = calls[0][0]
    output = Path(worker_command[worker_command.index("--out") + 1])
    assert output.is_relative_to(tmp_path) and output.name == "latest_checkpoint.json"
    if len(calls) == 2:
        tui_command = calls[1][0]
        assert tui_command[tui_command.index("--cohort-checkpoint") + 1] == str(output)
        assert "--detached-lifecycle" in tui_command
        assert "--cohort-command-inbox" not in tui_command
    assert tui.terminated == (case in {"worker_failure", "signal"})


def test_financial_launch_is_refused_before_child_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public monitor boundary rejects an execution-bearing launch object."""
    module = import_module("hypervector.live.cohort_independent_monitor")
    launcher = _load_module()
    launch = launcher.resolve_launch(
        launcher.build_parser().parse_args(["--mode", "monitor", "--config", str(CONFIG)]),
        credentials_present=False,
    )
    launch = replace(launch, backend_command=("forbidden-backend",))

    def refuse_spawn(*_args: object, **_kwargs: object) -> None:
        pytest.fail("an unauthorized child was started")

    monkeypatch.setattr(module.subprocess, "Popen", refuse_spawn)
    with pytest.raises(ValueError, match="independent monitor requires"):
        module.run_independent_monitor(launch, runtime_root=tmp_path)


def test_terminal_state_is_restored_after_reporter_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """A terminated native TUI must not leave the operator's terminal in raw mode."""
    module = import_module("hypervector.live.cohort_independent_monitor")
    restored: list[tuple[object, ...]] = []
    monkeypatch.setattr(module.sys, "stdin", SimpleNamespace(isatty=lambda: True, fileno=lambda: 88))
    monkeypatch.setattr(module.termios, "tcgetattr", lambda _fd: [1, 2, 3])
    monkeypatch.setattr(module.termios, "tcsetattr", lambda *args: restored.append(args))
    with pytest.raises(RuntimeError, match="reporter failed"):
        with module.preserve_terminal():
            raise RuntimeError("reporter failed")
    assert restored == [(88, module.termios.TCSADRAIN, [1, 2, 3])]
    assert "\x1b[?1049l\x1b[?25h\x1b[0m" in capsys.readouterr().out
