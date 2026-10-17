"""CLI boundary tests for recoverable transition-drain archival."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from types import ModuleType
from collections.abc import Iterator

from hypervector.live.cohort_transition_drain import CohortTransitionDrain

_RUN = "bidirectional-live-1785934800000"


def _load() -> ModuleType:
    return import_module("hypervector.operations.cohort_transition_drain_archive")


def _completed(path: Path) -> None:
    now = datetime(2026, 8, 5, 13, tzinfo=UTC)
    control = CohortTransitionDrain(
        path=path,
        run_id=_RUN,
        profile_fingerprint="a" * 64,
        now_fn=lambda: now,
    )
    control.activate(
        request_id="b" * 32,
        requested_at_utc="2026-08-05T12:59:59+00:00",
    )
    control.complete()


def test_dry_run_holds_runtime_lock_and_preserves_active_marker(tmp_path: Path) -> None:
    """The default command reports its destination without clearing evidence."""
    module = _load()
    state = tmp_path / "live/transition_drain.json"
    _completed(state)
    held: list[Path] = []

    @contextmanager
    def lock(ledger: Path) -> Iterator[Path]:
        held.append(ledger)
        yield ledger.parent / "process.lock"

    args = module.build_parser().parse_args(
        ["--state", str(state), "--expected-run-id", _RUN]
    )

    target = module.run_archive(
        args,
        lock_fn=lock,
        now_fn=lambda: datetime(2026, 8, 5, 14, tzinfo=UTC),
    )

    assert held == [state.parent / "decisions.jsonl"]
    assert state.is_file()
    assert not target.exists()


def test_confirmed_archive_preserves_bytes_and_clears_start_blocker(
    tmp_path: Path,
) -> None:
    """Explicit confirmation archives exact evidence while the backend is absent."""
    module = _load()
    state = tmp_path / "live/transition_drain.json"
    archive_root = tmp_path / "backups/drains"
    _completed(state)
    original = state.read_bytes()

    @contextmanager
    def lock(ledger: Path) -> Iterator[Path]:
        yield ledger.parent / "process.lock"

    args = module.build_parser().parse_args(
        [
            "--state",
            str(state),
            "--archive-root",
            str(archive_root),
            "--expected-run-id",
            _RUN,
            "--yes",
        ]
    )

    target = module.run_archive(
        args,
        lock_fn=lock,
        now_fn=lambda: datetime(2026, 8, 5, 14, tzinfo=UTC),
    )

    assert target.read_bytes() == original
    assert not state.exists()
