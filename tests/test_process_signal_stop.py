"""Process-level shutdown signal coverage for persistent live runtimes."""

from __future__ import annotations

import signal
from unittest.mock import Mock

import pytest

from hypervector.live.process_signal_stop import install_process_signal_stop


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
