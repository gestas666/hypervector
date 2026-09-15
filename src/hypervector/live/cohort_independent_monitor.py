"""Own a read-only reporter and TUI without owning the financial backend."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
import sys
import termios
import time
from uuid import uuid4

from hypervector.live.canary_supervisor import wait_for_checkpoint_readiness
from hypervector.live.cohort_monitor_identity import active_ledger_identity, fresh_checkpoint_document
from hypervector.live.cohort_tui_binary import verify_tui_command
from hypervector.live.cohort_tui_commands import CHECKPOINT_OUTPUT, MultiAssetTuiLaunch
from hypervector.live.cohort_tui_dependency_supervision import stop_owned_dependency
from hypervector.live.process_signal_stop import ProcessSignalStop

_WORKER = Path(__file__).resolve().parents[3] / "scripts/cohort_independent_monitor.py"
_POLL_SECONDS = 0.1
_FRESHNESS_SECONDS = 90.0


def run_independent_monitor(
    launch: MultiAssetTuiLaunch,
    *,
    runtime_root: Path = CHECKPOINT_OUTPUT.parent / "monitors",
    source_path: Path = CHECKPOINT_OUTPUT,
    stop: ProcessSignalStop | None = None,
) -> int:
    """Run and clean up only the two child processes created by this monitor."""
    _validate_monitor_launch(launch)
    active = active_ledger_identity(launch.config)
    if fresh_checkpoint_document(source_path, launch.config, maximum_age_seconds=_FRESHNESS_SECONDS) is None:
        raise ValueError(f"independent monitor requires a fresh shared reporter: {source_path}")
    session = runtime_root / uuid4().hex
    session.mkdir(parents=True)
    output, log = session / "latest_checkpoint.json", session / "checkpoint.log"
    monitored = replace(launch, tui_command=_tui_checkpoint(launch.tui_command, output))
    command = _worker_command(launch, source_path, output, active.run_id)
    latch = stop or ProcessSignalStop()
    with ExitStack() as cleanup, log.open("ab", buffering=0) as stream:
        worker = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream,
                                  stderr=subprocess.STDOUT, start_new_session=True)
        cleanup.callback(stop_owned_dependency, worker)
        wait_for_checkpoint_readiness(
            worker, is_fresh=lambda: _ready(monitored, output, latch),
            timeout_seconds=launch.startup_timeout_seconds, log_path=log,
        )
        cleanup.enter_context(preserve_terminal())
        verify_tui_command(monitored.tui_command, monitored.tui_binary)
        print(json.dumps({"event": "cohort_independent_monitor_ready", "checkpoint": str(output),
                          "reporter_pid": worker.pid,
                          "source": str(source_path), "execution_authority": "none"}), flush=True)
        tui = subprocess.Popen(monitored.tui_command)
        cleanup.callback(_stop_tui, tui)
        return _watch_children(tui, worker, log, latch)


@contextmanager
def preserve_terminal() -> Iterator[None]:
    """Restore terminal modes and the normal screen even after a child failure."""
    if not sys.stdin.isatty():
        yield
        return
    descriptor = sys.stdin.fileno()
    attributes = termios.tcgetattr(descriptor)
    try:
        yield
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, attributes)
        sys.stdout.write("\x1b[?1049l\x1b[?25h\x1b[0m")
        sys.stdout.flush()


def _validate_monitor_launch(launch: MultiAssetTuiLaunch) -> None:
    if (launch.backend_command is not None or launch.audit_command is not None
            or launch.dependency_command is not None
            or "--detached-lifecycle" not in launch.tui_command):
        raise ValueError("independent monitor requires an execution-incapable monitor launch")
    if not math.isfinite(launch.startup_timeout_seconds) or launch.startup_timeout_seconds <= 0:
        raise ValueError("independent monitor startup timeout must be positive and finite")
    verify_tui_command(launch.tui_command, launch.tui_binary)


def _tui_checkpoint(command: tuple[str, ...], output: Path) -> tuple[str, ...]:
    if command.count("--cohort-checkpoint") != 1:
        raise ValueError("independent TUI requires one checkpoint input")
    index = command.index("--cohort-checkpoint") + 1
    if index >= len(command):
        raise ValueError("independent TUI checkpoint input is missing")
    updated = list(command)
    updated[index] = str(output)
    if "--cohort-command-inbox" in updated:
        inbox = updated.index("--cohort-command-inbox")
        if updated.count("--cohort-command-inbox") != 1 or inbox + 1 >= len(updated):
            raise ValueError("independent TUI has a malformed operator inbox option")
        del updated[inbox:inbox + 2]
    return tuple(updated)


def _worker_command(
    launch: MultiAssetTuiLaunch, source: Path, output: Path, run_id: str,
) -> tuple[str, ...]:
    command = (sys.executable, str(_WORKER), "--worker", "--mode", "monitor",
               "--config", str(launch.config.source_path), "--run-id", run_id,
               "--source-checkpoint", str(source), "--out", str(output))
    checkpoint = launch.checkpoint_command or ()
    if "--accounting-epoch-bundle" in checkpoint:
        index = checkpoint.index("--accounting-epoch-bundle") + 1
        command += ("--accounting-epoch-bundle", checkpoint[index])
    return command


def _ready(launch: MultiAssetTuiLaunch, path: Path, stop: ProcessSignalStop) -> bool:
    if stop.requested:
        raise KeyboardInterrupt
    return path.is_file() and fresh_checkpoint_document(
        path, launch.config, maximum_age_seconds=_FRESHNESS_SECONDS,
    ) is not None


def _watch_children(
    tui: subprocess.Popen[bytes], worker: subprocess.Popen[bytes],
    log: Path, stop: ProcessSignalStop,
) -> int:
    while not stop.requested:
        result = tui.poll()
        if result is not None:
            return result
        result = worker.poll()
        if result is not None:
            raise RuntimeError(f"independent reporter exited with {result}; inspect {log}")
        time.sleep(_POLL_SECONDS)
    return 130


def _stop_tui(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)
