"""Checkpoint-readiness ordering for the cohort monitor TUI."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import signal
from types import ModuleType, SimpleNamespace

import pytest

from hypervector.live import canary_supervisor
from hypervector.live.canary_supervisor import wait_for_checkpoint_readiness

_SCRIPT = Path(__file__).parents[1] / "scripts/multi_asset_bidirectional_canary_tui.py"
_V14 = "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"


def _load_script() -> ModuleType:
    spec = spec_from_file_location("cohort_tui_checkpoint_readiness", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recovered_writer_refreshes_while_tui_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slow report-only recovery cannot block the operational cockpit."""
    module = _load_script()
    launch = module.resolve_launch(
        module.build_parser().parse_args(["--mode", "monitor", "--config", _V14]),
        credentials_present=False,
    )
    checkpoint = SimpleNamespace(label="checkpoint")
    calls: list[object] = []
    monkeypatch.setattr(module, "_checkpoint_is_fresh", lambda _config: False)
    monkeypatch.setattr(module, "cohort_checkpoint_writer_active", lambda _path: False)
    monkeypatch.setattr(
        module,
        "active_ledger_identity",
        lambda _config: SimpleNamespace(run_id="active-run"),
    )
    monkeypatch.setattr(
        module,
        "_start_checkpoint_monitor",
        lambda command: calls.append(("start", command)) or checkpoint,
    )
    monkeypatch.setattr(
        module,
        "_wait_for_monitor_checkpoint",
        lambda *_args, **_kwargs: pytest.fail(
            "monitor startup must not wait for checkpoint enrichment"
        ),
        raising=False,
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, *, check: calls.append(("tui", command))
        or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        module,
        "_stop_checkpoint_monitor",
        lambda process: calls.append(("stop", process.label)),
    )

    assert module.run_supervisor(launch) == 0
    assert [call[0] for call in calls] == ["start", "tui", "stop"]


def test_checkpoint_barrier_retries_until_exact_refresh() -> None:
    """Explicit readiness consumers wait without guessing success."""
    module = _load_script()
    launch = module.resolve_launch(
        module.build_parser().parse_args(["--mode", "monitor", "--config", _V14]),
        credentials_present=False,
    )
    freshness = iter((False, False, True))
    sleeps: list[float] = []
    process = SimpleNamespace(poll=lambda: None)

    wait_for_checkpoint_readiness(
        process,
        is_fresh=lambda: next(freshness),
        timeout_seconds=launch.startup_timeout_seconds,
        log_path=Path("checkpoint.log"),
        sleep_fn=sleeps.append,
        monotonic_fn=lambda: 0.0,
    )

    assert sleeps == [0.25, 0.25]


def test_checkpoint_barrier_reports_recovered_child_exit() -> None:
    """Explicit readiness consumers report a failed recovered writer."""
    module = _load_script()
    launch = module.resolve_launch(
        module.build_parser().parse_args(["--mode", "monitor", "--config", _V14]),
        credentials_present=False,
    )
    process = SimpleNamespace(poll=lambda: 3)

    with pytest.raises(RuntimeError, match="exited with 3"):
        wait_for_checkpoint_readiness(
            process,
            is_fresh=lambda: False,
            timeout_seconds=launch.startup_timeout_seconds,
            log_path=Path("checkpoint.log"),
        )


def test_checkpoint_monitor_starts_in_owned_process_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checkpoint descendants must be isolated for bounded supervisor cleanup."""
    module = _load_script()
    process = SimpleNamespace(label="checkpoint")
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
    monkeypatch.setattr(module, "_CHECKPOINT_LOG", tmp_path / "checkpoint.log")

    def popen(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(module.subprocess, "Popen", popen)

    assert module._start_checkpoint_monitor(("checkpoint",)) is process
    assert len(calls) == 1
    assert calls[0][1]["start_new_session"] is True


def test_checkpoint_monitor_stops_owned_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal TUI exit must stop the checkpoint and its research descendants."""
    module = _load_script()
    group_signals: list[tuple[int, signal.Signals]] = []
    parent_signals: list[str] = []

    class Process:
        pid = 321
        returncode = 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            parent_signals.append("terminate")

        def wait(self, *, timeout: float) -> int:
            assert timeout == 5.0
            return 0

    monkeypatch.setattr(
        module,
        "_signal_process_group",
        lambda process_group, sent_signal: group_signals.append(
            (process_group, sent_signal)
        ),
        raising=False,
    )

    assert module._stop_checkpoint_monitor(Process()) is None
    assert group_signals == [(321, signal.SIGTERM)]
    assert parent_signals == []


def test_checkpoint_monitor_force_stops_owned_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wedged writer and every descendant must receive the forced signal."""
    module = _load_script()
    group_signals: list[tuple[int, signal.Signals]] = []
    parent_signals: list[str] = []

    class Process:
        pid = 654
        returncode = 0
        wait_calls = 0

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            parent_signals.append("kill")

        def wait(self, *, timeout: float) -> int:
            assert timeout == 5.0
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise module.subprocess.TimeoutExpired("checkpoint", timeout)
            return 0

    monkeypatch.setattr(
        module,
        "_signal_process_group",
        lambda process_group, sent_signal: group_signals.append(
            (process_group, sent_signal)
        ),
    )

    failure = module._stop_checkpoint_monitor(Process())

    assert failure is not None and "forced termination" in failure
    assert group_signals == [
        (654, signal.SIGTERM),
        (654, signal.SIGKILL),
    ]
    assert parent_signals == []


def test_checkpoint_group_signal_tolerates_exit_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An already-exited checkpoint group is successful bounded cleanup."""

    def exited_group(_process_group: int, _sent_signal: signal.Signals) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(canary_supervisor.os, "killpg", exited_group)

    canary_supervisor.signal_process_group(987, signal.SIGTERM)
