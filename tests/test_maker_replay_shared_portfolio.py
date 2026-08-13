"""Shared-portfolio maker replay contracts for long/short challengers."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders


def _book(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """Build chronological BBO evidence from UTC timestamps."""
    return pd.DataFrame(
        {
            "ts_ms": [
                int(pd.Timestamp(timestamp).timestamp() * 1_000)
                for timestamp, _, _ in rows
            ],
            "best_bid": [bid for _, bid, _ in rows],
            "best_ask": [ask for _, _, ask in rows],
        }
    )


def test_decision_margin_stop_applies_only_to_the_tagged_entry() -> None:
    """A long stop annotation must not silently add a stop to a later short."""
    index = pd.to_datetime(
        [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:01:30Z",
            "2026-01-01T00:02:00Z",
        ],
        utc=True,
    )
    decisions = pd.DataFrame(
        {
            "entry_direction": ["long", None, "short"],
            "structural_direction": ["long", None, "short"],
            "entry_stop_margin_pct": [18.0, None, None],
        },
        index=index,
    )
    book = _book(
        [
            ("2026-01-01T00:01:00Z", 100.0, 101.0),
            ("2026-01-01T00:01:01Z", 98.0, 99.0),
            ("2026-01-01T00:01:02Z", 99.30, 99.40),
            ("2026-01-01T00:02:30Z", 100.0, 101.0),
            ("2026-01-01T00:03:00Z", 100.0, 101.0),
            ("2026-01-01T00:03:01Z", 102.0, 103.0),
        ]
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=15_000.0,
            margin_fraction=0.35,
            leverage=30.0,
            fill_rule="touch",
        ),
    )

    assert report.lifecycles[0].status == "stopped"
    assert report.lifecycles[0].stop_price == pytest.approx(99.40)
    assert report.lifecycles[1].status == "open"
    assert report.lifecycles[1].stop_price is None


def test_ignored_signal_does_not_cancel_an_existing_pending_entry() -> None:
    """An opposite annotation must not displace an already-pending order."""
    decisions = pd.DataFrame(
        {
            "entry_direction": ["long", None, "short"],
            "structural_direction": ["long", None, "short"],
        },
        index=pd.to_datetime(
            [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:01:05Z",
                "2026-01-01T00:01:10Z",
            ],
            utc=True,
        ),
    )
    book = _book(
        [
            ("2026-01-01T00:01:00Z", 100.0, 101.0),
            ("2026-01-01T00:02:05Z", 100.0, 101.0),
            ("2026-01-01T00:02:10Z", 100.0, 101.0),
            ("2026-01-01T00:02:11Z", 98.0, 99.0),
        ]
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            fill_rule="touch",
            entry_ttl_seconds=300.0,
            occupied_signal_policy="ignore",
        ),
    )

    assert report.submitted_entries == 1
    assert report.canceled_entries == 0
    assert report.entry_fills == 1
    assert report.lifecycles[0].direction == "long"


def test_ignored_signal_is_not_submitted_after_position_becomes_flat() -> None:
    """Only a fresh post-flat event may enter after an occupied annotation."""
    decisions = pd.DataFrame(
        {
            "entry_direction": ["long", None, "short", None, "short"],
            "structural_direction": ["long", None, "short", None, "short"],
        },
        index=pd.to_datetime(
            [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:01:05Z",
                "2026-01-01T00:01:10Z",
                "2026-01-01T00:03:30Z",
                "2026-01-01T00:03:35Z",
            ],
            utc=True,
        ),
    )
    book = _book(
        [
            ("2026-01-01T00:01:00Z", 100.0, 101.0),
            ("2026-01-01T00:01:01Z", 98.0, 99.0),
            ("2026-01-01T00:02:05Z", 100.0, 100.01),
            ("2026-01-01T00:02:10Z", 100.0, 100.01),
            ("2026-01-01T00:02:20Z", 100.30, 100.40),
            ("2026-01-01T00:02:21Z", 100.30, 100.40),
            ("2026-01-01T00:04:30Z", 100.0, 101.0),
            ("2026-01-01T00:04:35Z", 100.0, 101.0),
            ("2026-01-01T00:04:36Z", 102.0, 103.0),
        ]
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            fill_rule="touch",
            occupied_signal_policy="ignore",
        ),
    )

    assert report.submitted_entries == 2
    assert report.submission_times_utc == (
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:04:35+00:00",
    )
    assert [lifecycle.direction for lifecycle in report.lifecycles] == [
        "long",
        "short",
    ]
