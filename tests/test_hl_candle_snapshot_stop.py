"""A stopping live caller abandons a public candle read instead of waiting out its ladder.

Research callers pass no stop check and no timeout, and keep the 30 s, four-attempt
ladder exactly.
"""

from __future__ import annotations

from functools import partial
from unittest.mock import Mock

import pytest
import requests

from hypervector.data.hl import fetch_hl_ohlcv_snapshot
from hypervector.live.process_signal_stop import stop_aware_sleep

_END_MS = 1_785_585_600_000
_LIVE_TIMEOUT = (5.0, 10.0)


class _Stopped(Exception):
    """Stands in for the caller's own stop exception."""


class _Stop:
    """A caller stop that can be requested from inside a simulated request."""

    def __init__(self) -> None:
        self.requested = False
        self.checks = 0

    def check(self) -> None:
        self.checks += 1
        if self.requested:
            raise _Stopped


def _healthy() -> Mock:
    response = Mock(status_code=200, headers={})
    response.json.return_value = []
    return response


def _throttled(retry_after: str) -> Mock:
    response = Mock(status_code=429, headers={"Retry-After": retry_after})
    response.raise_for_status.side_effect = requests.HTTPError(
        "429 rate limited", response=response
    )
    return response


def test_default_read_keeps_the_research_ladder_exactly() -> None:
    session = Mock(spec=requests.Session)
    session.post.side_effect = requests.ConnectionError("venue unavailable")
    delays: list[float] = []

    with pytest.raises(requests.ConnectionError):
        fetch_hl_ohlcv_snapshot(
            "BTC", "1m", 14, session=session, end_ms=_END_MS, sleep_fn=delays.append
        )

    assert [call.kwargs["timeout"] for call in session.post.call_args_list] == [30] * 4
    assert delays == [1.0, 2.0, 4.0]


def test_live_timeout_reaches_every_attempt() -> None:
    session = Mock(spec=requests.Session)
    session.post.side_effect = [requests.ConnectionError("reset"), _healthy()]

    fetch_hl_ohlcv_snapshot(
        "BTC",
        "1m",
        14,
        session=session,
        end_ms=_END_MS,
        sleep_fn=lambda _seconds: None,
        timeout=_LIVE_TIMEOUT,
    )

    assert [call.kwargs["timeout"] for call in session.post.call_args_list] == [
        _LIVE_TIMEOUT,
        _LIVE_TIMEOUT,
    ]


def test_an_unrequested_stop_leaves_the_ladder_unchanged() -> None:
    session = Mock(spec=requests.Session)
    session.post.side_effect = requests.ConnectionError("venue unavailable")
    delays: list[float] = []
    stop = _Stop()

    with pytest.raises(requests.ConnectionError):
        fetch_hl_ohlcv_snapshot(
            "BTC",
            "1m",
            14,
            session=session,
            end_ms=_END_MS,
            sleep_fn=delays.append,
            stop_check=stop.check,
        )

    assert session.post.call_count == 4
    assert delays == [1.0, 2.0, 4.0]
    # Before and after every one of the four attempts.
    assert stop.checks == 8


def test_a_stop_before_a_read_sends_no_request() -> None:
    """The per-symbol check: the next symbol's read never starts after a stop."""
    session = Mock(spec=requests.Session)
    stop = _Stop()
    stop.requested = True

    with pytest.raises(_Stopped):
        fetch_hl_ohlcv_snapshot(
            "BTC", "1m", 14, session=session, end_ms=_END_MS, stop_check=stop.check
        )

    session.post.assert_not_called()


def test_a_stop_during_a_hung_read_abandons_the_ladder() -> None:
    """SIGTERM lands while a read hangs; its timeout ends the read, not three retries."""
    stop = _Stop()
    timeout = requests.ReadTimeout("read timed out")

    def hung(*_args: object, **_kwargs: object) -> Mock:
        stop.requested = True
        raise timeout

    session = Mock(spec=requests.Session)
    session.post.side_effect = hung
    delays: list[float] = []

    with pytest.raises(_Stopped) as caught:
        fetch_hl_ohlcv_snapshot(
            "BTC",
            "1m",
            14,
            session=session,
            end_ms=_END_MS,
            sleep_fn=delays.append,
            timeout=_LIVE_TIMEOUT,
            stop_check=stop.check,
        )

    assert session.post.call_count == 1
    assert delays == []
    assert caught.value.__context__ is timeout


def test_a_stop_during_a_retry_wait_prevents_the_next_attempt() -> None:
    stop = _Stop()
    session = Mock(spec=requests.Session)
    session.post.side_effect = [requests.ConnectionError("reset"), _healthy()]
    delays: list[float] = []

    def wait(seconds: float) -> None:
        delays.append(seconds)
        stop.requested = True

    with pytest.raises(_Stopped):
        fetch_hl_ohlcv_snapshot(
            "BTC",
            "1m",
            14,
            session=session,
            end_ms=_END_MS,
            sleep_fn=wait,
            stop_check=stop.check,
        )

    assert session.post.call_count == 1
    assert delays == [1.0]


def test_a_stop_during_a_throttled_read_skips_its_wait() -> None:
    """A 15 s Retry-After is not waited out once the backend is stopping."""
    stop = _Stop()
    throttled = _throttled("15")

    def respond(*_args: object, **_kwargs: object) -> Mock:
        stop.requested = True
        return throttled

    session = Mock(spec=requests.Session)
    session.post.side_effect = respond
    delays: list[float] = []

    with pytest.raises(_Stopped):
        fetch_hl_ohlcv_snapshot(
            "BTC",
            "1m",
            14,
            session=session,
            end_ms=_END_MS,
            sleep_fn=delays.append,
            stop_check=stop.check,
        )

    assert session.post.call_count == 1
    assert delays == []


def test_a_completed_read_is_returned_even_if_a_stop_arrived_meanwhile() -> None:
    """A finished read is never discarded; the next read is the one abandoned."""
    stop = _Stop()

    def respond(*_args: object, **_kwargs: object) -> Mock:
        stop.requested = True
        return _healthy()

    session = Mock(spec=requests.Session)
    session.post.side_effect = respond

    frame = fetch_hl_ohlcv_snapshot(
        "BTC", "1m", 14, session=session, end_ms=_END_MS, stop_check=stop.check
    )

    assert frame.empty
    assert session.post.call_count == 1


@pytest.mark.parametrize(
    ("retry_after", "waited"), [("nan", 1.0), ("NaN", 1.0), ("inf", 15.0)]
)
def test_a_non_finite_retry_after_cannot_break_the_live_wait(
    retry_after: str, waited: float
) -> None:
    """NaN falls back to the ladder delay; infinity keeps the existing 15 s cap.

    A NaN delay used to reach the wait, which rejects it with ValueError. That
    error is not a transport failure, so it escaped the degraded-read path and
    ended the live backend instead of retrying.
    """
    now = [0.0]

    def spend(seconds: float) -> None:
        now[0] += seconds

    live_wait = partial(
        stop_aware_sleep,
        stop_requested=lambda: False,
        sleep_fn=spend,
        monotonic_fn=lambda: now[0],
    )
    session = Mock(spec=requests.Session)
    session.post.side_effect = [_throttled(retry_after), _healthy()]

    frame = fetch_hl_ohlcv_snapshot(
        "BTC", "1m", 14, session=session, end_ms=_END_MS, sleep_fn=live_wait
    )

    assert frame.empty
    assert session.post.call_count == 2
    assert now[0] == waited
