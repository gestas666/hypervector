"""Chronological stop, liquidation, and optional target barrier tests."""

from __future__ import annotations

import pytest

from hypervector.research.range_onset_event_barriers import first_barrier_crossing
from hypervector.research.range_onset_event_models import EventReplayConfig
from hypervector.research.range_onset_event_risk import EventRiskPosition
from hypervector.research.shared_portfolio_models import Direction


def _position(direction: Direction = "long") -> EventRiskPosition:
    return EventRiskPosition(direction, 5.0, 100.0, 100.0, 0.225, 1_000, 99.4)


def test_target_precedes_later_stop() -> None:
    """A favorable crossing closes before a later adverse crossing."""

    def crossing(
        direction: Direction,
        boundary: float,
        _start_ms: int,
        _end_ms: int,
    ) -> int | None:
        if direction == "short" and boundary == pytest.approx(100.6):
            return 1_500
        if direction == "long" and boundary > 90.0:
            return 2_000
        return None

    result = first_barrier_crossing(
        _position(),
        (),
        EventReplayConfig(initial_equity=1_000.0, target_bps=60.0),
        crossing,
        3_000,
    )

    assert result is not None
    assert result.reason == "target"
    assert result.event_time_ms == 1_500


def test_adverse_barrier_wins_same_timestamp_ambiguity() -> None:
    """A same-timestamp stop/target ambiguity uses conservative ordering."""

    def crossing(
        direction: Direction,
        boundary: float,
        _start_ms: int,
        _end_ms: int,
    ) -> int | None:
        if direction == "long" and boundary < 90.0:
            return None
        return 1_500

    result = first_barrier_crossing(
        _position(),
        (),
        EventReplayConfig(initial_equity=1_000.0, target_bps=60.0),
        crossing,
        3_000,
    )

    assert result is not None
    assert result.reason == "stop"


def test_none_target_preserves_existing_adverse_contract() -> None:
    """The default no-target contract must not query a favorable barrier."""
    queried: list[Direction] = []

    def crossing(
        direction: Direction,
        boundary: float,
        _start_ms: int,
        _end_ms: int,
    ) -> int | None:
        queried.append(direction)
        return 1_500 if boundary > 90.0 else None

    result = first_barrier_crossing(
        _position(),
        (),
        EventReplayConfig(initial_equity=1_000.0),
        crossing,
        3_000,
    )

    assert result is not None
    assert result.reason == "stop"
    assert set(queried) == {"long"}
