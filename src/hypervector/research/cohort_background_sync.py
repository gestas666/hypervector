"""Non-blocking research synchronization for the live checkpoint publisher."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import shutil

SyncFn = Callable[[Path, Path], Mapping[str, object]]
_MINIMUM_RESEARCH_SYNC_FREE_BYTES = 8 * 1024**3


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
        minimum_free_bytes: int = _MINIMUM_RESEARCH_SYNC_FREE_BYTES,
        portfolio_archive: Mapping[str, object] | None = None,
    ) -> None:
        if interval_seconds <= 0.0:
            raise ValueError("research sync interval must be positive")
        if minimum_free_bytes < 0:
            raise ValueError("research sync minimum free bytes cannot be negative")
        self._database_path = database_path
        self._ledger_root = ledger_root
        self._interval_seconds = interval_seconds
        self._minimum_free_bytes = minimum_free_bytes
        self._sync_fn = sync_fn
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._future: Future[Mapping[str, object]] | None = None
        self._next_sync_at = 0.0
        self.portfolio_archive = portfolio_archive
        self.report: dict[str, object] | None = None
        self.error: str | None = None

    def poll(self, *, now: float) -> None:
        """Consume a completed worker and schedule another without waiting."""
        if self._consume_completed():
            self._next_sync_at = now + self._interval_seconds
        if self._future is None and now >= self._next_sync_at:
            if not self._has_disk_headroom():
                self._next_sync_at = now + self._interval_seconds
                return
            self._future = self._executor.submit(
                self._sync_fn,
                self._database_path,
                self._ledger_root,
            )
            self._next_sync_at = now + self._interval_seconds

    def _has_disk_headroom(self) -> bool:
        try:
            available = shutil.disk_usage(self._database_path.parent).free
        except OSError as exc:
            self.error = f"research sync deferred: disk headroom unavailable: {exc}"
            return False
        if available >= self._minimum_free_bytes:
            return True
        self.error = (
            "research sync deferred: available disk space is below the "
            f"required {self._minimum_free_bytes} bytes"
        )
        return False

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

    def _consume_completed(self) -> bool:
        if self._future is None or not self._future.done():
            return False
        future = self._future
        self._future = None
        try:
            result = future.result()
            archive = _portfolio_archive(result)
        except ResearchSyncError as exc:
            self.error = str(exc)
            return True
        if archive is not None:
            self.portfolio_archive = archive
        self.report = {
            key: value for key, value in result.items() if key != "portfolio_archive"
        }
        self.error = None
        return False


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
