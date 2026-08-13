"""Shared process-local signal latch for bounded backend shutdown."""

from __future__ import annotations

from dataclasses import dataclass
import signal


@dataclass
class ProcessSignalStop:
    """Record termination requests for handling between protected operations."""

    requested: bool = False

    def request(self, _signum: int, _frame: object) -> None:
        """Latch one signal without interrupting the active operation."""
        self.requested = True


def install_process_signal_stop() -> ProcessSignalStop:
    """Install interrupt, termination, and terminal-hangup stop handlers."""
    stop = ProcessSignalStop()
    signal.signal(signal.SIGINT, stop.request)
    signal.signal(signal.SIGTERM, stop.request)
    signal.signal(signal.SIGHUP, stop.request)
    return stop
