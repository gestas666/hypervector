"""Fail-closed startup tests shared by every staged canary supervisor."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.canary_supervisor import (
    CanarySupervisorError,
    capture_ledger_start,
    wait_for_fresh_configuration_identity,
)


class RunningBackend:
    """Controllable child-process status for startup polling."""

    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode

    def poll(self) -> int | None:
        """Return the configured process status."""
        return self.returncode


class ManualClock:
    """Deterministic monotonic clock advanced only by test sleep calls."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        """Return deterministic elapsed time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance deterministic elapsed time."""
        self.now += seconds


def test_missing_ledger_captures_an_empty_append_boundary(tmp_path: Path) -> None:
    """A first run can establish identity in a ledger that does not yet exist."""
    snapshot = capture_ledger_start(tmp_path / "missing.jsonl")

    assert snapshot.initial_size == 0
    assert snapshot.prior_run_ids == frozenset()


@pytest.mark.parametrize(
    "content",
    [
        b'{"run_id":"incomplete"}',
        b"\xff\n",
        b"not-json\n",
        b"[]\n",
    ],
)
def test_existing_malformed_ledger_fails_before_backend_launch(
    tmp_path: Path,
    content: bytes,
) -> None:
    """Corrupt prior telemetry cannot be accepted as a safe append boundary."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_bytes(content)

    with pytest.raises(CanarySupervisorError):
        capture_ledger_start(ledger)


def test_nonpositive_startup_timeout_is_refused(tmp_path: Path) -> None:
    """A zero timeout cannot silently bypass the fresh-identity gate."""
    ledger = tmp_path / "decisions.jsonl"

    with pytest.raises(CanarySupervisorError, match="must be positive"):
        wait_for_fresh_configuration_identity(
            RunningBackend(),
            ledger,
            snapshot=capture_ledger_start(ledger),
            expected_profile_fingerprint="profile",
            expected_live_armed=False,
            timeout_seconds=0.0,
            backend_label="test",
            log_path=tmp_path / "backend.log",
        )


def test_backend_exit_is_reported_before_tui_launch(tmp_path: Path) -> None:
    """A child that fails before identity publication cannot open the TUI."""
    ledger = tmp_path / "decisions.jsonl"

    with pytest.raises(CanarySupervisorError, match="exited with 2"):
        wait_for_fresh_configuration_identity(
            RunningBackend(returncode=2),
            ledger,
            snapshot=capture_ledger_start(ledger),
            expected_profile_fingerprint="profile",
            expected_live_armed=True,
            timeout_seconds=1.0,
            backend_label="test",
            log_path=tmp_path / "backend.log",
        )


def test_timeout_reports_missing_fresh_identity(tmp_path: Path) -> None:
    """An active child without matching telemetry eventually fails explicitly."""
    ledger = tmp_path / "decisions.jsonl"
    clock = ManualClock()

    with pytest.raises(CanarySupervisorError, match="not ready after 0.1s"):
        wait_for_fresh_configuration_identity(
            RunningBackend(),
            ledger,
            snapshot=capture_ledger_start(ledger),
            expected_profile_fingerprint="profile",
            expected_live_armed=True,
            timeout_seconds=0.1,
            backend_label="test",
            log_path=tmp_path / "backend.log",
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
        )


def test_ledger_truncation_is_rejected_during_startup(tmp_path: Path) -> None:
    """A backend cannot replace historical evidence while claiming readiness."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(
        '{"event_type":"configuration_identity","run_id":"old-long-run"}\n',
        encoding="utf-8",
    )
    snapshot = capture_ledger_start(ledger)
    ledger.write_text("{}\n", encoding="utf-8")

    with pytest.raises(CanarySupervisorError, match="non-append-only"):
        wait_for_fresh_configuration_identity(
            RunningBackend(),
            ledger,
            snapshot=snapshot,
            expected_profile_fingerprint="profile",
            expected_live_armed=False,
            timeout_seconds=1.0,
            backend_label="test",
            log_path=tmp_path / "backend.log",
        )


def test_partial_appended_identity_waits_until_row_is_complete(tmp_path: Path) -> None:
    """An in-progress JSONL write is retried rather than parsed as corruption."""
    ledger = tmp_path / "decisions.jsonl"
    snapshot = capture_ledger_start(ledger)
    ledger.write_text(
        '{"event_type":"configuration_identity","run_id":"fresh",',
        encoding="utf-8",
    )
    clock = ManualClock()
    sleeps = 0

    def complete_row(seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        clock.sleep(seconds)
        ledger.write_text(
            '{"event_type":"configuration_identity","run_id":"fresh",'
            '"profile_fingerprint":"profile","live_armed":false}\n',
            encoding="utf-8",
        )

    wait_for_fresh_configuration_identity(
        RunningBackend(),
        ledger,
        snapshot=snapshot,
        expected_profile_fingerprint="profile",
        expected_live_armed=False,
        timeout_seconds=1.0,
        backend_label="test",
        log_path=tmp_path / "backend.log",
        sleep_fn=complete_row,
        monotonic_fn=clock.monotonic,
    )

    assert sleeps == 1


def test_invalid_complete_appended_row_is_rejected(tmp_path: Path) -> None:
    """A newline-terminated corrupt row is a fault rather than a retry."""
    ledger = tmp_path / "decisions.jsonl"
    snapshot = capture_ledger_start(ledger)
    ledger.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(CanarySupervisorError, match="invalid JSON"):
        wait_for_fresh_configuration_identity(
            RunningBackend(),
            ledger,
            snapshot=snapshot,
            expected_profile_fingerprint="profile",
            expected_live_armed=False,
            timeout_seconds=1.0,
            backend_label="test",
            log_path=tmp_path / "backend.log",
        )
