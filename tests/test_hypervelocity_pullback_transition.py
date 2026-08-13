"""Causal tests for target-completion pullback-transition re-entry."""

from __future__ import annotations

import pandas as pd

from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders
from hypervector.research.maker_replay_signals import available_reentry_events
from hypervector.research.maker_replay_stream import (
    MakerReplayEvidenceChunk,
    replay_maker_order_chunks,
)


def _decisions(states: list[str]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(states), freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "entry_direction": ["long"] * len(states),
            "structural_direction": ["long"] * len(states),
            "state_1m": states,
        },
        index=index,
    )


def _book(seconds: list[int], bids: list[float], asks: list[float]) -> pd.DataFrame:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    timestamps = [origin + pd.Timedelta(seconds=value) for value in seconds]
    return pd.DataFrame(
        {
            "ts_ms": [int(value.timestamp() * 1_000) for value in timestamps],
            "best_bid": bids,
            "best_ask": asks,
        }
    )


def _config() -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=100.0,
        maker_fee_rate=0.0,
        fill_rule="touch",
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy="target_pullback_transition",
        target_continuation_limit_per_episode=6,
    )


def test_pullback_reentry_events_are_causal_state_transitions() -> None:
    decisions = _decisions(
        ["TREND_UP", "RANGE", "RANGE", "TREND_DOWN", "TREND_UP", "RANGE"]
    )

    events = available_reentry_events(decisions)

    assert events.index.equals(decisions.index + pd.Timedelta(minutes=1))
    assert events.tolist() == [None, "long", None, "long", None, "long"]


def test_pullback_transition_policy_accepts_source_bounded_controls() -> None:
    config = MakerReplayConfig(
        same_direction_reentry_policy="target_pullback_transition",
        target_continuation_limit_per_episode=6,
        target_continuation_minimum_episode_seconds=1_800.0,
    )

    assert config.target_continuation_limit_per_episode == 6
    assert config.target_continuation_minimum_episode_seconds == 1_800.0


def test_pullback_reentry_requires_fresh_post_cooldown_transition() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80, 140, 239, 240, 250, 260],
            [100.0, 99.0, 100.2, 100.0, 100.0, 100.0, 99.0, 100.2],
            [101.0, 100.0, 100.3, 101.0, 101.0, 101.0, 100.0, 100.3],
        ),
        _decisions(["TREND_UP", "TREND_UP", "TREND_UP", "RANGE", "RANGE"]),
        _config(),
    )

    assert report.completed_trades == 2
    assert report.submission_times_utc == (
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:04:00+00:00",
    )


def test_pullback_transition_before_target_cannot_be_reused() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 120, 130, 190],
            [100.0, 99.0, 100.0, 100.2, 100.0],
            [101.0, 100.0, 101.0, 100.3, 101.0],
        ),
        _decisions(["TREND_UP", "RANGE", "RANGE", "RANGE"]),
        _config(),
    )

    assert report.completed_trades == 1
    assert report.submitted_entries == 1


def test_pullback_transition_streaming_matches_single_chunk() -> None:
    first = _book(
        [60, 70, 80, 140],
        [100.0, 99.0, 100.2, 100.0],
        [101.0, 100.0, 100.3, 101.0],
    )
    second = _book(
        [239, 240, 250, 260],
        [100.0, 100.0, 99.0, 100.2],
        [101.0, 101.0, 100.0, 100.3],
    )
    decisions = _decisions(["TREND_UP", "TREND_UP", "TREND_UP", "RANGE", "RANGE"])
    combined = pd.concat((first, second), ignore_index=True)

    batch = replay_maker_orders(combined, decisions, _config())
    streamed = replay_maker_order_chunks(
        (MakerReplayEvidenceChunk(first), MakerReplayEvidenceChunk(second)),
        decisions,
        _config(),
    )

    assert streamed.to_dict() == batch.to_dict()
