"""Deterministic time controls for the native poll and receipt replay."""

from datetime import UTC, datetime
from decimal import localcontext

import pytest

from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_events import Stamp


def test_clock_separates_elapsed_time_and_same_millisecond_event_order() -> None:
    """Native wall and monotonic callbacks advance only through explicit replay."""
    clock = ReplayClock(1_000)
    assert clock.now() == datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC)
    assert clock.monotonic() == 0
    assert clock.next_stamp() == Stamp(1_000, 0)
    assert clock.next_stamp() == Stamp(1_000, 1)
    clock.advance_to(1_000)
    assert clock.next_stamp() == Stamp(1_000, 2)
    clock.sleep(0.001)
    assert clock.now_ms == 1_001
    assert clock.monotonic() == 0.001
    assert clock.next_stamp() == Stamp(1_001, 0)
    clock.sleep(0)
    assert clock.next_stamp() == Stamp(1_001, 1)


@pytest.mark.parametrize("seconds", [-1, float("nan"), float("inf"), True, 0.0001, "1"])
def test_bad_sleep_durations_leave_the_clock_unchanged(seconds: object) -> None:
    """Refuse ambiguous, negative or sub-millisecond waits instead of rounding."""
    clock = ReplayClock(1_000)
    with pytest.raises(ValueError):
        clock.sleep(seconds)
    assert clock.now_ms == 1_000


@pytest.mark.parametrize("stamp", [-1, True, 0.1, 10**20])
def test_invalid_initial_clocks_are_rejected(stamp: object) -> None:
    """Keep every accepted millisecond representable by the native UTC callback."""
    with pytest.raises(ValueError):
        ReplayClock(stamp)


def test_clock_cannot_rewind_after_a_delayed_receipt() -> None:
    """A subsequent event must not erase elapsed acquisition or delivery time."""
    clock = ReplayClock(1_000)
    clock.advance_to(2_000)
    with pytest.raises(ValueError, match="backwards"):
        clock.advance_to(1_500)
    assert clock.now_ms == 2_000


def test_native_float_subtraction_does_not_create_a_fractional_sleep_error() -> None:
    """Whole-ms native elapsed time can have IEEE subtraction residue."""
    clock = ReplayClock(0)
    clock.sleep(15.0 - (12.977 - 1.0))
    assert clock.now_ms == 3_023


def test_sleep_does_not_inherit_decimal_rounding_settings() -> None:
    """An unrelated Decimal precision must not round an explicit sleep duration."""
    with localcontext() as context:
        context.prec = 4
        clock = ReplayClock(0)
        clock.sleep(1234.567)
    assert clock.now_ms == 1_234_567
