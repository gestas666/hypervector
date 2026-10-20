"""Configuration, ownership and persistence boundaries for process supervision."""

import json
from pathlib import Path

import pytest

from cohort_supervisor_models import HealthThresholds, RestartPolicy
from cohort_supervisor_state import RestartJournal, supervisor_lock


@pytest.mark.parametrize("value", [-1.0, 0.0, float("inf"), float("nan")])
def test_health_thresholds_require_finite_positive_limits(value: float) -> None:
    """An invalid threshold must fail before any supervisor or watchdog starts."""
    with pytest.raises(ValueError):
        HealthThresholds(heartbeat_seconds=value)


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_restart_count_requires_nonnegative_integer(value: object) -> None:
    """Nonintegral or negative retry allowances cannot silently alter policy."""
    with pytest.raises(ValueError):
        RestartPolicy(maximum_restarts=value)


def test_second_supervisor_is_refused_while_first_owns_lock(tmp_path: Path) -> None:
    """The ownership lock covers startup and backoff, when no backend may exist."""
    with supervisor_lock(tmp_path / "events.jsonl"):
        with pytest.raises(ValueError, match="another supervisor"):
            with supervisor_lock(tmp_path / "events.jsonl"):
                pytest.fail("second supervisor acquired ownership")


def test_reservation_before_spawn_survives_replacement(tmp_path: Path) -> None:
    """Crashing between a reservation and spawn cannot grant an uncharged attempt."""
    path = tmp_path / "events.jsonl"
    first = RestartJournal(path, ["backend"])
    policy = RestartPolicy(maximum_restarts=0)
    assert first.reserve(100.0, policy)
    second = RestartJournal(path, ["backend"])
    assert not second.reserve(101.0, policy)
    assert second.hold_reason == "restart_budget_exhausted"


def test_changed_command_requires_explicit_journal_archive(tmp_path: Path) -> None:
    """A service definition edit cannot reuse authority for a different command."""
    path = tmp_path / "events.jsonl"
    RestartJournal(path, ["backend-a"]).reserve(100.0, RestartPolicy())
    with pytest.raises(ValueError, match="command changed"):
        RestartJournal(path, ["backend-b"])


@pytest.mark.parametrize(
    "update",
    [
        {"schema_version": 0},
        {"launch_times": [float("nan")]},
        {"launch_times": [True]},
        {"hold_reason": []},
    ],
)
def test_invalid_journal_schema_is_refused(
    tmp_path: Path, update: dict[str, object]
) -> None:
    """Malformed durable history does not become an empty retry allowance."""
    journal = RestartJournal(tmp_path / "events.jsonl", ["backend"])
    journal.reserve(100.0, RestartPolicy())
    payload = json.loads(journal.path.read_text())
    journal.path.write_text(json.dumps({**payload, **update}))
    with pytest.raises(ValueError):
        RestartJournal(tmp_path / "events.jsonl", ["backend"])


def test_backwards_wall_clock_latches_hold(tmp_path: Path) -> None:
    """A clock regression cannot discard prior launches from accounting."""
    journal = RestartJournal(tmp_path / "events.jsonl", ["backend"])
    assert journal.reserve(100.0, RestartPolicy())
    assert not journal.reserve(99.0, RestartPolicy())
    assert journal.hold_reason == "restart_clock_moved_backwards"
