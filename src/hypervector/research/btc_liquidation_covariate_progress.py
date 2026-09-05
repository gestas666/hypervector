"""Bounded secret-free progress for BTC covariate acquisition."""

from __future__ import annotations

from dataclasses import dataclass
import json

from hypervector.data.oxa_backfill import OxaBackfillResult


@dataclass
class ProgressReporter:
    """Emit aggregate resumable-acquisition counters at a bounded cadence."""

    expected: int
    every: int
    completed: int = 0
    downloaded: int = 0
    resumed: int = 0
    rows: int = 0
    pages: int = 0

    def __post_init__(self) -> None:
        if self.expected < 1 or self.every < 1:
            raise ValueError("progress bounds must be positive")

    def __call__(self, result: OxaBackfillResult) -> None:
        """Record one completed task and emit only at the bounded cadence."""
        self.completed += 1
        self.downloaded += int(not result.skipped)
        self.resumed += int(result.skipped)
        self.rows += result.rows
        self.pages += result.pages
        if self.completed % self.every == 0 or self.completed == self.expected:
            print(json.dumps(self.payload(), sort_keys=True), flush=True)

    def payload(self) -> dict[str, int | str]:
        """Return the current credential-free progress record."""
        return {
            "event": "btc_liquidation_covariate_progress",
            "completed": self.completed,
            "expected": self.expected,
            "downloaded": self.downloaded,
            "resumed": self.resumed,
            "rows": self.rows,
            "pages": self.pages,
        }
