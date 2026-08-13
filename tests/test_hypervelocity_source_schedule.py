"""Source-scheduled Hypervelocity replay tests."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hypervelocity_reentry_compare import (
    logical_source_positions,
)
from hypervector.research.hypervelocity_source_schedule import (
    merge_supplemental_positions,
    source_schedule_decisions,
)
from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders
from hypervector.research.maker_replay_signals import available_directions


def _records() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "record_source": [
                "position_peak_only",
                "trade_only",
                "position_peak+trade",
                "position_peak_only",
            ],
            "trade_id": [None, 10, 11, None],
            "symbol": ["BTC"] * 4,
            "side": ["long", "long", "long", "short"],
            "status": ["closed"] * 4,
            "open_time_utc": [
                "2026-01-01T00:01:00Z",
                "2026-01-01T00:01:10Z",
                "2026-01-01T00:01:10.500Z",
                "2026-01-01T00:03:00Z",
            ],
            "close_time_utc": [
                "2026-01-01T00:02:00Z",
                "2026-01-01T00:02:05Z",
                "2026-01-01T00:02:05Z",
                "2026-01-01T00:04:00Z",
            ],
            "entry_price": [100.0, 100.0, 100.0, 99.0],
            "exit_price": [100.2, 100.2, 100.25, None],
            "quantity": [0.01, 0.01, 0.005, 0.02],
        }
    )


def test_logical_source_positions_reconcile_duplicates_and_split_exits() -> None:
    logical = logical_source_positions(_records())

    assert len(logical) == 2
    assert logical.iloc[0]["source_rows"] == 2
    assert logical.iloc[0]["timestamp_provenance"] == "trade_backed"
    assert logical.iloc[0]["open_ts"] == pd.Timestamp("2026-01-01T00:01:10Z")
    assert logical.iloc[1]["timestamp_provenance"] == "tracker_only"


def test_source_schedule_becomes_exact_one_shot_available_directions() -> None:
    logical = logical_source_positions(_records())

    decisions = source_schedule_decisions(logical)
    available = available_directions(decisions)
    signals = available.loc[available.notna()]

    assert list(signals.index) == [
        pd.Timestamp("2026-01-01T00:01:10Z"),
        pd.Timestamp("2026-01-01T00:03:00Z"),
    ]
    assert signals.tolist() == ["long", "short"]
    first_reset = pd.Timestamp("2026-01-01T00:01:05Z")
    assert pd.isna(
        decisions.loc[first_reset - pd.Timedelta(minutes=1)]["structural_direction"]
    )


def test_source_schedule_does_not_resubmit_between_declared_events() -> None:
    logical = pd.DataFrame(
        {
            "open_ts": pd.to_datetime(
                ["2026-01-01T00:01:00Z", "2026-01-01T00:03:00Z"], utc=True
            ),
            "side": ["long", "long"],
            "timestamp_provenance": ["trade_backed", "trade_backed"],
        }
    )
    decisions = source_schedule_decisions(logical)
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    seconds = [55, 60, 70, 80, 175, 180, 190, 200]
    book = pd.DataFrame(
        {
            "ts_ms": [
                int((origin + pd.Timedelta(seconds=value)).timestamp() * 1000)
                for value in seconds
            ],
            "best_bid": [100.0, 100.0, 99.0, 100.2] * 2,
            "best_ask": [101.0, 101.0, 100.0, 100.3] * 2,
        }
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            reentry_cooldown_seconds=60.0,
            same_direction_reentry_policy="cooldown_only",
        ),
    )

    assert report.submitted_entries == 2
    assert report.completed_trades == 2
    first_exit = pd.Timestamp(report.lifecycles[0].outcome_time_utc)
    second_entry = pd.Timestamp(report.lifecycles[1].entry_time_utc)
    assert first_exit < second_entry


def test_screenshot_outcome_replaces_matching_tracker_and_adds_new_entry() -> None:
    logical = pd.DataFrame(
        {
            "open_ts": pd.to_datetime(["2026-07-24T15:06:32.209297Z"], utc=True),
            "side": ["short"],
            "entry_price": [63_893.0],
            "timestamp_provenance": ["tracker_only"],
        }
    )
    supplemental = pd.DataFrame(
        {
            "open_time_utc": [
                "2026-07-24T15:06:32.209297Z",
                "2026-07-25T18:50:00Z",
            ],
            "side": ["short", "long"],
            "entry_price": [63_893.0, 64_395.0],
            "exit_price": [63_766.0, 64_523.0],
            "outcome_time_utc": [None, None],
        }
    )

    merged = merge_supplemental_positions(logical, supplemental)

    assert len(merged) == 2
    assert merged["side"].tolist() == ["short", "long"]
    assert merged["timestamp_provenance"].tolist() == [
        "screenshot_outcome_backed",
        "screenshot_outcome_backed",
    ]
    assert merged["exit_price"].tolist() == [63_766.0, 64_523.0]
    assert merged["close_ts"].isna().all()
