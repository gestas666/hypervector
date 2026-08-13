"""Visible-depth diagnostics for observer one-blocker replay attempts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hypervector.research.cohort_observer_depth_diagnostics import (
    build_attempt_entry_depth_diagnostics,
)


def test_top_level_failure_can_resolve_against_exact_visible_depth() -> None:
    """A multi-level walk distinguishes thin BBO from inadequate depth."""
    report = build_attempt_entry_depth_diagnostics(
        _replay(),
        _books(),
    )

    assert report["attempt_count"] == 1
    row = report["attempts"][0]
    assert row["replay_status"] == "entry_capacity_failures"
    assert row["top_level_complete"] is False
    assert row["visible_depth_complete"] is True
    assert row["levels_consumed"] == 2
    assert row["visible_vwap"] == pytest.approx(100.18999, rel=1e-4)
    assert report["fills_claimed"] is False


def test_missing_or_late_exact_book_remains_unresolved() -> None:
    """The diagnostic must not extrapolate beyond the recorded entry delay."""
    books = _books()
    payload = books[0]["payload"]
    assert isinstance(payload, dict)
    payload["recv_ts_ms"] = 2_100

    report = build_attempt_entry_depth_diagnostics(_replay(), books)

    assert report["attempts"][0]["status"] == "entry_book_missing"
    assert report["visible_depth_complete_count"] == 0


def _replay() -> dict[str, object]:
    return {
        "contract": {
            "symbol": "HYPE",
            "notional_usd": 100.0,
            "maximum_entry_delay_ms": 1_000,
        },
        "attempts": [
            {
                "symbol": "HYPE",
                "side": "long",
                "decision_time_ms": 0,
                "available_time_ms": 1_000,
                "status": "entry_capacity_failures",
            }
        ],
    }


def _books() -> tuple[dict[str, object], ...]:
    return (
        {
            "event_type": "book_observation",
            "observed_at_utc": datetime.fromtimestamp(1.6, timezone.utc).isoformat(),
            "payload": {
                "symbol": "HYPE",
                "recv_ts_ms": 1_500,
                "mid_px": 100.0,
                "bids": [{"price": 99.9, "size": 2.0}],
                "asks": [
                    {"price": 100.1, "size": 0.1},
                    {"price": 100.2, "size": 1.0},
                ],
            },
        },
    )
