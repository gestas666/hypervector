"""Creator-alignment tests for raw-regime reset re-entry evidence."""

from __future__ import annotations

import pandas as pd

from hypervector.research.source_reentry_raw_reset import raw_reset_reentry_evidence


def test_raw_reset_report_separates_hidden_from_confirmed_resets() -> None:
    """A raw-only reset is distinct from an ordinary confirmed regime reset."""
    report = raw_reset_reentry_evidence(_positions(), _labels())

    assert report["logical_positions"] == 3
    assert report["same_side_nonoverlapping_reentries"] == 2
    assert report["raw_reset_return_windows"] == 2
    assert report["hidden_raw_reset_return_windows"] == 1
    assert report["raw_side_aligned_at_entry"] == 2
    assert report["confirmed_side_aligned_at_entry"] == 2
    assert report["windows"][0]["raw_reset_return"] is True
    assert report["windows"][0]["confirmed_reset"] is False
    assert report["windows"][1]["confirmed_reset"] is True


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_utc": [
                "2026-07-01T00:00:00Z",
                "2026-07-01T00:15:00Z",
                "2026-07-01T00:30:00Z",
            ],
            "close_time_utc": [
                "2026-07-01T00:05:00Z",
                "2026-07-01T00:20:00Z",
                "2026-07-01T00:35:00Z",
            ],
            "side": ["short", "short", "short"],
            "entry_price": [100.0, 99.0, 98.0],
            "exit_price": [99.0, 98.0, 97.0],
            "status": ["closed", "closed", "closed"],
        }
    )


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                [
                    "2026-07-01T00:10:00Z",
                    "2026-07-01T00:15:00Z",
                    "2026-07-01T00:25:00Z",
                    "2026-07-01T00:30:00Z",
                ],
                utc=True,
            ),
            "primary_code": [
                "TREND_DOWN",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
            ],
            "secondary_code": [None, None, None, None],
            "raw_primary_code": ["RANGE", "TREND_DOWN", "RANGE", "TREND_DOWN"],
            "raw_secondary_code": [None, None, None, None],
        }
    )
