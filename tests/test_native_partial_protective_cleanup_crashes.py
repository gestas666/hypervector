"""Process-death boundaries must preserve completed exit economics without duplicate dispatch."""

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from test_native_partial_protective_recovery import assert_closed_economics, restart
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.asset_protective_cleanup_checkpoint import CLEANUP_PHASE

__all__ = ["deny_external_ports"]


class CrashDuringCleanup(BaseException):
    """Simulate process death after a durable write, bypassing ordinary exception recovery."""


@pytest.mark.parametrize("boundary", ["marker", "cancel_ack", "completion"])
@pytest.mark.parametrize("aged_out", [False, True])
def test_cleanup_crash_and_aged_out_history_recover_without_duplicate_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str, aged_out: bool
) -> None:
    """Original recorded receipts remain authoritative after current fill history expires."""
    replay, original = _partial_fixture(tmp_path, "BTC", "stop", False, Decimal("0.5"))
    events = replay.engines["BTC"]._events
    emit, emit_ack = events.emit, events.emit_ack

    def crash_emit(kind: str, payload: Mapping[str, object]) -> None:
        emit(kind, payload)
        marker = kind == "close" and payload.get("phase") == CLEANUP_PHASE
        complete = kind == "close" and payload.get("verified_flat") is True
        if (boundary == "marker" and marker) or (boundary == "completion" and complete):
            raise CrashDuringCleanup()

    def crash_ack(
        operation: str, ack: HyperliquidOrderAck, *, event_type: str = "order_acknowledgement"
    ) -> None:
        emit_ack(operation, ack, event_type=event_type)
        if boundary == "cancel_ack" and operation == "cancel_residual_after_close":
            raise CrashDuringCleanup()

    monkeypatch.setattr(events, "emit", crash_emit)
    monkeypatch.setattr(events, "emit_ack", crash_ack)
    with pytest.raises(CrashDuringCleanup):
        replay.engines["BTC"].reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms, funding_end_time_ms=replay.clock.now_ms
        )
    if aged_out:
        replay._info.user_fills.side_effect = lambda address: []
    restart(replay, "BTC")
    assert replay.mutations.count("close") == replay.mutations.count("cancel") == 1
    assert_closed_economics(replay, "BTC")
    complete = [
        row
        for row in replay.engines["BTC"]._ledger.read_all()
        if row["event_type"] == "close" and row["payload"].get("verified_flat") is True
    ]
    assert len(complete) == 1
