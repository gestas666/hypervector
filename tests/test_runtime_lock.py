"""Advisory process locks for the cohort, its observer, checkpoints and live-run."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import hypervector.runtime_lock as runtime_lock
from hypervector.runtime_lock import (
    bidirectional_live_runtime_lock,
    bidirectional_observer_runtime_lock,
    generic_live_runtime_lock,
)


def test_cohort_checkpoint_writer_lock_is_exclusive_and_observable(
    tmp_path: Path,
) -> None:
    """Only one sidecar may replace a bounded checkpoint artifact."""
    output = tmp_path / "runtime" / "latest_checkpoint.json"
    lock_fn = getattr(runtime_lock, "cohort_checkpoint_runtime_lock", None)
    active_fn = getattr(runtime_lock, "cohort_checkpoint_writer_active", None)
    assert lock_fn is not None
    assert active_fn is not None

    assert active_fn(output) is False
    with lock_fn(output) as lock_path:
        assert lock_path == output.parent / "latest_checkpoint.json.writer.lock"
        assert active_fn(output) is True
        with pytest.raises(RuntimeError, match="checkpoint writer already running"):
            with lock_fn(output):
                pytest.fail("second checkpoint writer acquired the same output")

    assert active_fn(output) is False


def test_cohort_live_lock_is_exclusive_and_reacquirable(tmp_path: Path) -> None:
    """Only one live cohort process may own its ledger and the account."""
    ledger = tmp_path / "data/live/bidirectional_cohort/decisions.jsonl"

    with bidirectional_live_runtime_lock(ledger) as lock_path:
        assert lock_path == ledger.parent / "process.lock"
        with pytest.raises(RuntimeError, match="bidirectional live cohort already"):
            with bidirectional_live_runtime_lock(ledger):
                pytest.fail("second cohort acquired the same lock")

    with bidirectional_live_runtime_lock(ledger):
        pass


def test_released_pid_file_does_not_claim_account_ownership(tmp_path: Path) -> None:
    """A stale file is not an active owner without a held kernel lock."""
    live_root = tmp_path / "data/live"
    stale = live_root / "bidirectional_cohort/process.lock"
    stale.parent.mkdir(parents=True)
    stale.write_text(str(os.getpid()), encoding="utf-8")

    with generic_live_runtime_lock(live_root):
        pass


def test_cohort_and_generic_live_daemon_share_one_account_authority(
    tmp_path: Path,
) -> None:
    """The cohort and the generic live-run daemon never trade one account together."""
    live_root = tmp_path / "data/live"
    cohort = live_root / "bidirectional_cohort/decisions.jsonl"

    with bidirectional_live_runtime_lock(cohort):
        with pytest.raises(RuntimeError, match="shared live account"):
            with generic_live_runtime_lock(live_root):
                pytest.fail("live-run bypassed cohort account ownership")

    with generic_live_runtime_lock(live_root):
        with pytest.raises(RuntimeError, match="shared live account"):
            with bidirectional_live_runtime_lock(cohort):
                pytest.fail("cohort bypassed live-run account ownership")

    with bidirectional_live_runtime_lock(cohort):
        pass


def test_bidirectional_observer_and_live_backend_are_mutually_exclusive(
    tmp_path: Path,
) -> None:
    """A disarmed observer cannot interleave rows with the live cohort."""
    ledger = tmp_path / "data/live/bidirectional_cohort/decisions.jsonl"

    with bidirectional_observer_runtime_lock(ledger):
        with pytest.raises(RuntimeError, match="bidirectional cohort observer"):
            with bidirectional_live_runtime_lock(ledger):
                pytest.fail("live cohort bypassed the active observer")

    with bidirectional_live_runtime_lock(ledger):
        with pytest.raises(RuntimeError, match="bidirectional live cohort"):
            with bidirectional_observer_runtime_lock(ledger):
                pytest.fail("observer bypassed the active live cohort")
