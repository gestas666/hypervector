"""Tests for bounded BTC covariate-acquisition progress reporting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from hypervector.data.oxa_backfill import OxaBackfillResult, OxaBackfillTask


def test_progress_reporter_emits_bounded_secret_free_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Long resumable acquisition should report counts, not credentials."""
    from hypervector.research.btc_liquidation_covariate_progress import (
        ProgressReporter,
    )

    reporter = ProgressReporter(expected=2, every=2)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    tasks = (
        OxaBackfillTask("book", start, start + timedelta(hours=1)),
        OxaBackfillTask("trade", start, start + timedelta(hours=1)),
    )
    reporter(OxaBackfillResult(tasks[0], Path("book"), True, 10, 1))
    reporter(OxaBackfillResult(tasks[1], Path("trade"), False, 20, 2))

    output = capsys.readouterr().out.strip().splitlines()
    assert len(output) == 1
    assert json.loads(output[0]) == {
        "completed": 2,
        "downloaded": 1,
        "event": "btc_liquidation_covariate_progress",
        "expected": 2,
        "pages": 3,
        "resumed": 1,
        "rows": 30,
    }
