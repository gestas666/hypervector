"""Non-blocking research synchronization for the live checkpoint publisher."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

SyncFn = Callable[[Path, Path], Mapping[str, object]]


class ResearchSyncError(RuntimeError):
    """Raised when report-only cohort evidence cannot be persisted."""


class BackgroundResearchSync:
    """Run at most one slow research sync outside the checkpoint hot path."""

    def __init__(
        self,
        database_path: Path,
        ledger_root: Path,
        interval_seconds: float,
        sync_fn: SyncFn,
        *,
        portfolio_archive: Mapping[str, object] | None = None,
    ) -> None:
        if interval_seconds <= 0.0:
            raise ValueError("research sync interval must be positive")
        self._database_path = database_path
        self._ledger_root = ledger_root
        self._interval_seconds = interval_seconds
        self._sync_fn = sync_fn
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._future: Future[Mapping[str, object]] | None = None
        self._next_sync_at = 0.0
        self.portfolio_archive = portfolio_archive
        self.report: dict[str, object] | None = None
        self.error: str | None = None

    def poll(self, *, now: float) -> None:
        """Consume a completed worker and schedule another without waiting."""
        self._consume_completed()
        if self._future is None and now >= self._next_sync_at:
            self._future = self._executor.submit(
                self._sync_fn,
                self._database_path,
                self._ledger_root,
            )
            self._next_sync_at = now + self._interval_seconds

    def wait_for_completion(self, *, timeout: float) -> None:
        """Wait explicitly for deterministic tests or bounded shutdown tooling."""
        if self._future is not None:
            self._future.result(timeout=timeout)

    def close(self) -> None:
        """Reject queued work without waiting on an already running worker."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    def pop_report(self) -> dict[str, object] | None:
        """Return one completed sync report without repeating it."""
        report = self.report
        self.report = None
        return report

    def pop_error(self) -> str | None:
        """Return one explicit worker failure without repeating it."""
        error = self.error
        self.error = None
        return error

    def _consume_completed(self) -> None:
        if self._future is None or not self._future.done():
            return
        future = self._future
        self._future = None
        try:
            result = future.result()
        except ResearchSyncError as exc:
            self.error = str(exc)
            return
        archive = _portfolio_archive(result)
        if archive is not None:
            self.portfolio_archive = archive
        self.report = {
            key: value for key, value in result.items() if key != "portfolio_archive"
        }
        self.error = None


def _portfolio_archive(
    result: Mapping[str, object],
) -> Mapping[str, object] | None:
    archive = result.get("portfolio_archive")
    if archive is None:
        return None
    if not isinstance(archive, Mapping):
        raise ResearchSyncError("research worker portfolio archive must be an object")
    if archive.get("schema_version") != 1:
        raise ResearchSyncError(
            "research worker portfolio archive schema is unsupported"
        )
    if archive.get("mode") != "cohort_live_portfolio_archive_v1":
        raise ResearchSyncError("research worker portfolio archive mode is unsupported")
    return archive
