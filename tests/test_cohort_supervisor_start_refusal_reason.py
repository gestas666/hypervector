"""A held start refusal names its reason in the supervisor's durable journal.

A venue contract refusal found before the pre-start bundle happens before the
cohort ledger is opened, so the backend's own journal holds no row for it; its
reason is the one stderr line the backend prints before exiting 2.
"""

from __future__ import annotations

from pathlib import Path
import sys
import textwrap
import threading
import time

import cohort_backend_supervisor as sup
from test_cohort_backend_supervisor import FAKE_HOST, FAST, _events, _paths, _Recorder

REFUSING = textwrap.dedent(
    """
    import os, sys
    root, message = sys.argv[1], sys.argv[2]
    open(os.path.join(root, "process.lock"), "w").write(str(os.getpid()))
    print("venue start probe passed: markets=8 attempts=1")
    if message:
        print("live start refused: " + message, file=sys.stderr)
    sys.exit(2)
    """
)


def _supervise_one_refusal(tmp_path: Path, message: str) -> list[dict[str, object]]:
    script = tmp_path / "refusing_backend.py"
    script.write_text(REFUSING, encoding="utf-8")
    stop = sup._StopFlag()

    def release_hold() -> None:
        events = tmp_path / "events.jsonl"
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if events.exists() and '"holding"' in events.read_text():
                break
            time.sleep(0.01)
        stop.requested = True

    releaser = threading.Thread(target=release_hold)
    releaser.start()
    paths = _paths(tmp_path)
    code = sup.supervise(
        [sys.executable, str(script), str(tmp_path), message],
        paths,
        sup.HealthThresholds(),
        FAST,
        sup.Alerter([_Recorder()]),
        interval=0.02,
        working_directory=tmp_path,
        runtime=sup.SupervisorRuntime(
            is_backend=lambda _pid: False, deadman=lambda _url: None, **FAKE_HOST
        ),
        stop=stop,
    )
    releaser.join()
    assert code == 0
    return [e for e in _events(paths) if e["event"] == "restart_decision"]


def test_a_refused_start_journals_the_backend_reason(tmp_path: Path) -> None:
    reason = "xyz:EEE max leverage mismatch: expected 20, observed 10"

    decisions = _supervise_one_refusal(tmp_path, reason)

    assert len(decisions) == 1
    assert decisions[0]["reason"] == "live_start_refused_fail_closed"
    assert decisions[0]["exit_code"] == 2
    assert decisions[0]["refusal_reason"] == reason


def test_an_earlier_launchs_refusal_is_never_attributed(tmp_path: Path) -> None:
    """Only output written by this launch can name this launch's refusal."""
    (tmp_path / "child.log").write_text(
        "live start refused: stale reason from yesterday\n", encoding="utf-8"
    )

    decisions = _supervise_one_refusal(tmp_path, "")

    assert len(decisions) == 1
    assert decisions[0]["reason"] == "live_start_refused_fail_closed"
    assert "refusal_reason" not in decisions[0]


def test_a_long_refusal_is_bounded(tmp_path: Path) -> None:
    decisions = _supervise_one_refusal(tmp_path, "x" * 5_000)

    assert decisions[0]["refusal_reason"] == "x" * 500
