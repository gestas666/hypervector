"""Failed or ambiguous temporal source events cannot disappear behind a later replay clock."""

import pytest
from test_native_replay_adapter import deny_external_ports
from test_native_replay_sdk import sdk

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("clock", [999, True, 1.1, -1])
def test_invalid_event_clock_does_not_advance_account(clock: object) -> None:
    """Prior, boolean and fractional event clocks are explicit input failures."""
    replay = sdk()
    with pytest.raises(ValueError):
        replay.schedule(clock, "event", lambda r: None)
    assert replay.clock.now_ms == 1000


def test_duplicate_identity_cannot_replace_a_pending_event() -> None:
    """A conflict must not substitute a different settlement callback."""
    replay = sdk()
    observed: list[str] = []
    replay.schedule(1050, "same", lambda r: observed.append("original"))
    with pytest.raises(ValueError, match="unique ID"):
        replay.schedule(1050, "same", lambda r: observed.append("replacement"))
    replay.advance_to(1050)
    assert observed == ["original"]


def test_failed_callback_is_retained_and_does_not_report_later_time() -> None:
    """An external data failure propagates and remains reproducible on a second attempt."""
    replay = sdk()
    seen: list[int] = []

    def fail() -> None:
        seen.append(replay.clock.now_ms)
        raise RuntimeError("source unavailable")

    replay.timeline.schedule(1050, "bad-source", fail)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="source unavailable"):
            replay.advance_to(1200)
        assert replay.clock.now_ms == 1050
    assert seen == [1050, 1050]


@pytest.mark.parametrize("raw", [False, True])
def test_event_callback_cannot_advance_its_own_clock(raw: bool) -> None:
    """Nested response waits or raw jumps would make event ordering ambiguous."""
    replay = sdk()
    replay.schedule(
        1050, "recursive", lambda r: (r.clock if raw else r.runtime_clock).advance_to(1100)
    )
    with pytest.raises(ValueError, match="raw clock" if raw else "recurse"):
        replay.advance_to(1200)
    assert replay.clock.now_ms < 1200


def test_runtime_and_account_stamps_share_a_single_sequence() -> None:
    """Native waits cannot restart the account's same-millisecond sequence counter."""
    replay = sdk()
    first = replay.runtime_clock.next_stamp()
    second = replay.clock.next_stamp()
    assert second.sequence == first.sequence + 1
    with pytest.raises(ValueError, match="backwards"):
        replay.runtime_clock.advance_to(999)
