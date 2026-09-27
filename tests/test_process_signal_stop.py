"""Process-level shutdown signal coverage for persistent live runtimes."""

from __future__ import annotations

from collections.abc import Iterator
import signal
import threading
import time
from unittest.mock import Mock

import pytest

from hypervector.live.process_signal_stop import (
    STOP_CHECK_SECONDS,
    ProcessSignalStop,
    ProcessStopRequested,
    install_process_signal_stop,
    raise_if_stop_requested,
    stop_aware_sleep,
)

_HANDLED = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class _Clock:
    """A monotonic clock that moves only when the wait spends it."""

    def __init__(self, stop_at: float | None = None) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.stop_at = stop_at

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def stopped(self) -> bool:
        return self.stop_at is not None and self.now >= self.stop_at


@pytest.fixture
def restored_signal_handlers() -> Iterator[None]:
    """Let one test install the real latch without leaking it into the session."""
    saved = {signum: signal.getsignal(signum) for signum in _HANDLED}
    try:
        yield
    finally:
        for signum, handler in saved.items():
            signal.signal(signum, handler)


def _signal_main_thread_after(seconds: float) -> threading.Timer:
    main = threading.main_thread().ident
    assert main is not None
    timer = threading.Timer(seconds, signal.pthread_kill, (main, signal.SIGTERM))
    timer.start()
    return timer


def test_live_stop_latch_handles_terminal_hangup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lost controlling terminal must request a journaled graceful stop."""
    installed: dict[signal.Signals, object] = {}

    def capture(signum: signal.Signals, handler: object) -> Mock:
        installed[signum] = handler
        return Mock()

    monkeypatch.setattr(signal, "signal", capture)

    stop = install_process_signal_stop()

    assert set(installed) == {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}
    handler = installed[signal.SIGHUP]
    assert callable(handler)
    handler(signal.SIGHUP, None)
    assert stop.requested is True


def test_install_arms_the_latch_already_handed_to_read_only_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The candle reads and the run loop must observe one and the same latch."""
    installed: dict[signal.Signals, object] = {}

    def capture(signum: signal.Signals, handler: object) -> Mock:
        installed[signum] = handler
        return Mock()

    monkeypatch.setattr(signal, "signal", capture)
    latch = ProcessSignalStop()

    assert install_process_signal_stop(latch) is latch
    handler = installed[signal.SIGTERM]
    assert callable(handler)
    handler(signal.SIGTERM, None)
    assert latch.requested is True


def test_idle_wait_spends_its_full_period_in_bounded_slices() -> None:
    clock = _Clock()

    stop_aware_sleep(
        4.5,
        stop_requested=lambda: False,
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
    )

    assert clock.sleeps == [1.0, 1.0, 1.0, 1.0, 0.5]
    assert clock.now == 4.5


def test_stop_mid_wait_returns_within_one_slice() -> None:
    """A stop 3.2 s into a 15 s poll wait is honoured at the next slice boundary."""
    clock = _Clock(stop_at=3.2)

    stop_aware_sleep(
        15.0,
        stop_requested=clock.stopped,
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
    )

    assert clock.now == 4.0
    assert clock.now - 3.2 <= STOP_CHECK_SECONDS


def test_a_stop_already_requested_skips_the_wait() -> None:
    clock = _Clock(stop_at=0.0)

    stop_aware_sleep(
        15.0,
        stop_requested=clock.stopped,
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
    )

    assert clock.sleeps == []


def test_zero_wait_does_not_sleep() -> None:
    clock = _Clock()

    stop_aware_sleep(
        0.0,
        stop_requested=lambda: False,
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
    )

    assert clock.sleeps == []


@pytest.mark.parametrize("seconds", [-1.0, float("nan"), float("inf")])
def test_an_invalid_wait_is_refused(seconds: float) -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        stop_aware_sleep(seconds, stop_requested=lambda: False, sleep_fn=Mock())


@pytest.mark.parametrize("slice_seconds", [0.0, -1.0, float("nan")])
def test_an_invalid_slice_is_refused(slice_seconds: float) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        stop_aware_sleep(
            1.0,
            stop_requested=lambda: False,
            sleep_fn=Mock(),
            slice_seconds=slice_seconds,
        )


def test_read_only_work_is_abandoned_only_after_a_stop() -> None:
    requested = False

    raise_if_stop_requested(lambda: requested)
    requested = True

    with pytest.raises(ProcessStopRequested):
        raise_if_stop_requested(lambda: requested)


@pytest.mark.usefixtures("restored_signal_handlers")
def test_a_handled_signal_does_not_end_a_plain_sleep_early() -> None:
    """The defect being fixed: PEP 475 resumes time.sleep after the handler runs."""
    latch = install_process_signal_stop()
    timer = _signal_main_thread_after(0.1)
    started = time.monotonic()
    try:
        time.sleep(0.6)
    finally:
        timer.cancel()

    assert latch.requested is True
    assert time.monotonic() - started >= 0.55


@pytest.mark.usefixtures("restored_signal_handlers")
def test_a_real_termination_signal_ends_the_stop_aware_wait_early() -> None:
    """SIGTERM 0.2 s into a 30 s wait returns within one production slice."""
    latch = install_process_signal_stop()
    timer = _signal_main_thread_after(0.2)
    started = time.monotonic()
    try:
        stop_aware_sleep(30.0, stop_requested=lambda: latch.requested)
    finally:
        timer.cancel()

    assert latch.requested is True
    assert time.monotonic() - started < 0.2 + STOP_CHECK_SECONDS + 1.0
