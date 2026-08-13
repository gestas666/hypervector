"""Single-backend runtime locking for one Hypervelocity data root."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
import os
from pathlib import Path

import pytest

import hypervector.runtime_lock as runtime_lock
from hypervector.runtime_lock import (
    apex_mm_live_runtime_lock,
    bidirectional_live_runtime_lock,
    bidirectional_observer_runtime_lock,
    hulk_smash_live_runtime_lock,
    hulk_smash_observer_runtime_lock,
    hypervelocity_runtime_lock,
    source_follow_live_runtime_lock,
)

LiveLock = Callable[[Path], AbstractContextManager[Path]]


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


def test_second_backend_for_same_root_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "ops"

    with hypervelocity_runtime_lock(root):
        with pytest.raises(RuntimeError, match="already running"):
            with hypervelocity_runtime_lock(root):
                pytest.fail("second backend acquired the same lock")


def test_lock_is_released_after_backend_stops(tmp_path: Path) -> None:
    root = tmp_path / "ops"

    with hypervelocity_runtime_lock(root):
        pass
    with hypervelocity_runtime_lock(root):
        pass


def test_sol_live_lock_is_exclusive_and_reacquirable(tmp_path: Path) -> None:
    """Only one live process may own a canary ledger at a time."""
    ledger = tmp_path / "data" / "live" / "sol" / "decisions.jsonl"

    with runtime_lock.sol_live_runtime_lock(ledger) as lock_path:
        assert lock_path == ledger.parent / "process.lock"
        with pytest.raises(RuntimeError, match="SOL live backend already running"):
            with runtime_lock.sol_live_runtime_lock(ledger):
                pytest.fail("second live backend acquired the same lock")

    with runtime_lock.sol_live_runtime_lock(ledger):
        pass


def test_btc_live_lock_refuses_active_sol_account_owner(tmp_path: Path) -> None:
    """Independent live strategies cannot allocate the same canary balance."""
    btc_ledger = tmp_path / "data/live/hypervelocity_source_follow/decisions.jsonl"
    sol_ledger = tmp_path / "data/live/sol_range_onset_canary/decisions.jsonl"

    with runtime_lock.sol_live_runtime_lock(sol_ledger):
        with pytest.raises(RuntimeError, match="shared live account"):
            with source_follow_live_runtime_lock(btc_ledger):
                pytest.fail("BTC acquired a shared account with active SOL authority")


@pytest.mark.parametrize(
    ("owner_directory", "owner_label"),
    [
        ("sol_range_onset_canary", "SOL live backend"),
        ("hypervelocity_source_follow", "BTC source-follow live backend"),
    ],
)
def test_apex_mm_lock_refuses_other_active_account_owner(
    tmp_path: Path,
    owner_directory: str,
    owner_label: str,
) -> None:
    """A standalone MM canary cannot bypass another account owner."""
    apex_ledger = tmp_path / "data/live/apex_regime_mm/decisions.jsonl"
    owner_ledger = tmp_path / "data/live" / owner_directory / "decisions.jsonl"
    owner_lock = (
        runtime_lock.sol_live_runtime_lock
        if owner_directory == "sol_range_onset_canary"
        else source_follow_live_runtime_lock
    )

    with owner_lock(owner_ledger):
        with pytest.raises(RuntimeError, match="shared live account"):
            with apex_mm_live_runtime_lock(apex_ledger):
                pytest.fail(f"Apex MM bypassed active {owner_label}")


def test_released_pid_file_does_not_claim_account_ownership(tmp_path: Path) -> None:
    """A stale file is not an active owner without a held kernel lock."""
    apex_ledger = tmp_path / "data/live/apex_regime_mm/decisions.jsonl"
    stale = tmp_path / "data/live/sol_range_onset_canary/process.lock"
    stale.parent.mkdir(parents=True)
    stale.write_text(str(os.getpid()), encoding="utf-8")

    with apex_mm_live_runtime_lock(apex_ledger):
        pass


def test_apex_mm_lock_is_exclusive_and_reacquirable(tmp_path: Path) -> None:
    """Only one Apex MM live process may own its lifecycle."""
    ledger = tmp_path / "data/live/apex_regime_mm/decisions.jsonl"

    with apex_mm_live_runtime_lock(ledger) as lock_path:
        assert lock_path == ledger.parent / "process.lock"
        with pytest.raises(RuntimeError, match="Apex MM live backend already running"):
            with apex_mm_live_runtime_lock(ledger):
                pytest.fail("second Apex MM backend acquired the lock")

    with apex_mm_live_runtime_lock(ledger):
        pass


def test_hulk_live_and_observer_cannot_append_to_same_ledger(tmp_path: Path) -> None:
    """The read-only observer and live backend cannot corrupt one JSONL sequence."""
    ledger = tmp_path / "data/live/hulk_smash/decisions.jsonl"

    with hulk_smash_observer_runtime_lock(ledger):
        with pytest.raises(RuntimeError, match="Hulk Smash observer"):
            with hulk_smash_live_runtime_lock(ledger):
                pytest.fail("Hulk live bypassed the active observer")

    with hulk_smash_live_runtime_lock(ledger):
        with pytest.raises(RuntimeError, match="Hulk Smash live backend"):
            with hulk_smash_observer_runtime_lock(ledger):
                pytest.fail("observer bypassed the active Hulk live backend")


def test_hulk_live_lock_is_exclusive_and_reacquirable(tmp_path: Path) -> None:
    """Only one Hulk execution lifecycle can own the account and ledger."""
    ledger = tmp_path / "data/live/hulk_smash/decisions.jsonl"

    with hulk_smash_live_runtime_lock(ledger):
        with pytest.raises(RuntimeError, match="Hulk Smash live backend"):
            with hulk_smash_live_runtime_lock(ledger):
                pytest.fail("second Hulk live backend acquired the lock")

    with hulk_smash_live_runtime_lock(ledger):
        pass


def test_bidirectional_cohort_owns_one_shared_account_lock(tmp_path: Path) -> None:
    """One cohort process may own both sleeves while standalones stay excluded."""
    live_root = tmp_path / "data/live"
    cohort = live_root / "bidirectional_cohort/decisions.jsonl"
    hulk = live_root / "hulk_smash/decisions.jsonl"
    sol = live_root / "sol_range_onset_canary/decisions.jsonl"

    with bidirectional_live_runtime_lock(cohort) as lock_path:
        assert lock_path == cohort.parent / "process.lock"
        with pytest.raises(RuntimeError, match="shared live account"):
            with hulk_smash_live_runtime_lock(hulk):
                pytest.fail("standalone Hulk bypassed cohort account ownership")
        with pytest.raises(RuntimeError, match="shared live account"):
            with runtime_lock.sol_live_runtime_lock(sol):
                pytest.fail("standalone SOL bypassed cohort account ownership")


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


def test_cohort_refuses_existing_standalone_owner_and_is_reacquirable(
    tmp_path: Path,
) -> None:
    """Cohort startup cannot weaken current standalone exclusion guarantees."""
    live_root = tmp_path / "data/live"
    cohort = live_root / "bidirectional_cohort/decisions.jsonl"
    hulk = live_root / "hulk_smash/decisions.jsonl"

    with hulk_smash_live_runtime_lock(hulk):
        with pytest.raises(RuntimeError, match="shared live account"):
            with bidirectional_live_runtime_lock(cohort):
                pytest.fail("cohort bypassed standalone account ownership")

    with bidirectional_live_runtime_lock(cohort):
        pass


@pytest.mark.parametrize(
    ("owner_lock", "owner_directory", "contender_lock", "contender_directory"),
    [
        (
            hulk_smash_live_runtime_lock,
            "hulk_smash",
            apex_mm_live_runtime_lock,
            "apex_regime_mm",
        ),
        (
            apex_mm_live_runtime_lock,
            "apex_regime_mm",
            hulk_smash_live_runtime_lock,
            "hulk_smash",
        ),
        (
            hulk_smash_live_runtime_lock,
            "hulk_smash",
            runtime_lock.sol_live_runtime_lock,
            "sol_range_onset_canary",
        ),
        (
            runtime_lock.sol_live_runtime_lock,
            "sol_range_onset_canary",
            hulk_smash_live_runtime_lock,
            "hulk_smash",
        ),
        (
            apex_mm_live_runtime_lock,
            "apex_regime_mm",
            runtime_lock.sol_live_runtime_lock,
            "sol_range_onset_canary",
        ),
        (
            runtime_lock.sol_live_runtime_lock,
            "sol_range_onset_canary",
            apex_mm_live_runtime_lock,
            "apex_regime_mm",
        ),
    ],
)
def test_live_candidate_locks_are_mutually_exclusive(
    tmp_path: Path,
    owner_lock: LiveLock,
    owner_directory: str,
    contender_lock: LiveLock,
    contender_directory: str,
) -> None:
    """Every selected canary must share one exclusive account authority."""
    owner = tmp_path / "data/live" / owner_directory / "decisions.jsonl"
    contender = tmp_path / "data/live" / contender_directory / "decisions.jsonl"

    with owner_lock(owner):
        with pytest.raises(RuntimeError, match="shared live account"):
            with contender_lock(contender):
                pytest.fail("two selected canaries acquired the same live account")
