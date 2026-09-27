"""Shared process-local signal latch for bounded backend shutdown."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import signal
import time

# How long an idle wait can outlast a stop request.
STOP_CHECK_SECONDS = 1.0


@dataclass
class ProcessSignalStop:
    """Record termination requests for handling between protected operations."""

    requested: bool = False

    def request(self, _signum: int, _frame: object) -> None:
        """Latch one signal without interrupting the active operation."""
        self.requested = True


class ProcessStopRequested(Exception):
    """A requested stop abandoned read-only work that had not yet finished."""


def install_process_signal_stop(
    stop: ProcessSignalStop | None = None,
) -> ProcessSignalStop:
    """Install interrupt, termination, and terminal-hangup stop handlers.

    A caller that has already handed ``stop`` to read-only work passes it here,
    so those reads and the run loop observe the same latch.
    """
    stop = ProcessSignalStop() if stop is None else stop
    signal.signal(signal.SIGINT, stop.request)
    signal.signal(signal.SIGTERM, stop.request)
    signal.signal(signal.SIGHUP, stop.request)
    return stop


def stop_aware_sleep(
    seconds: float,
    *,
    stop_requested: Callable[[], bool],
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    slice_seconds: float = STOP_CHECK_SECONDS,
) -> None:
    """Wait up to ``seconds``, returning within one slice of a requested stop.

    A handled signal does not end ``time.sleep`` early: PEP 475 resumes it for
    the time that remained. Waiting in bounded slices and re-checking the stop
    between them is what bounds the stop latency of an idle backend.
    """
    if not math.isfinite(seconds) or seconds < 0.0:
        raise ValueError("wait must be finite and nonnegative")
    if not math.isfinite(slice_seconds) or slice_seconds <= 0.0:
        raise ValueError("stop check slice must be positive and finite")
    deadline = monotonic_fn() + seconds
    while not stop_requested():
        remaining = deadline - monotonic_fn()
        if remaining <= 0.0:
            return
        sleep_fn(min(slice_seconds, remaining))


def raise_if_stop_requested(stop_requested: Callable[[], bool]) -> None:
    """Abandon read-only work once a stop has been requested."""
    if stop_requested():
        raise ProcessStopRequested("backend stop requested")
