"""Ordering tests for durable SOL live mutation intent."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from unittest.mock import Mock

import pytest

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
)
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


_CLIENT_ORDER_ID = "0x0123456789abcdef0123456789abcdef"


class RecordingEventSink:
    """Record intent events in the same timeline as venue mutations."""

    def __init__(self, timeline: list[tuple[str, object]]) -> None:
        self._timeline = timeline

    def emit(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record one event without transforming its payload."""
        self._timeline.append((event_type, dict(payload)))

    def fault(self, reason: str) -> None:
        """Record an unresolved technical mutation fault."""
        self._timeline.append(("fault", reason))


def test_entry_intent_precedes_authenticated_submission() -> None:
    """A crash or timeout cannot erase which exact entry was attempted."""
    from hypervector.live.sol_order_submission import SolOrderSubmission

    timeline: list[tuple[str, object]] = []
    adapter = Mock()

    def submit_entry(**kwargs: object) -> HyperliquidOrderAck:
        timeline.append(("venue_submit_entry", dict(kwargs)))
        return HyperliquidOrderAck(
            True,
            101,
            "filled",
            client_order_id=_CLIENT_ORDER_ID,
        )

    adapter.submit_entry.side_effect = submit_entry
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink(timeline),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
    )

    ack = submission.submit_entry(
        side="long",
        requested_notional_usd=22.50,
        mark_price=73.0,
    )

    assert ack.client_order_id == _CLIENT_ORDER_ID
    assert timeline[0] == (
        "order_intent",
        {
            "operation": "entry",
            "client_order_id": _CLIENT_ORDER_ID,
            "side": "long",
            "requested_notional_usd": 22.50,
            "mark_price": 73.0,
        },
    )
    assert timeline[1][0] == "venue_submit_entry"
    assert isinstance(timeline[1][1], dict)
    assert timeline[1][1]["client_order_id"] == _CLIENT_ORDER_ID


def test_order_intent_is_a_durable_live_ledger_event(tmp_path: Path) -> None:
    """The append-only ledger accepts intent before any venue acknowledgement."""
    path = tmp_path / "data/live/sol_range_onset_canary/decisions.jsonl"
    ledger = SolLiveLedger(
        path=path,
        profile_id="profile",
        profile_fingerprint="profile-hash",
        run_fingerprint="run-hash",
        run_id="run-test",
    )

    ledger.append(
        event_type="order_intent",
        observed_at_utc="2026-07-31T12:00:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={
            "operation": "entry",
            "client_order_id": _CLIENT_ORDER_ID,
        },
    )

    records = ledger.read_all()
    assert records[0]["event_type"] == "order_intent"
    assert records[0]["payload"]["client_order_id"] == _CLIENT_ORDER_ID


def test_stop_intent_precedes_authenticated_submission() -> None:
    """Native protection is recoverable even when its HTTP response is lost."""
    from hypervector.live.sol_order_submission import SolOrderSubmission

    timeline: list[tuple[str, object]] = []
    adapter = Mock()

    def place_stop(**kwargs: object) -> HyperliquidOrderAck:
        timeline.append(("venue_place_stop", dict(kwargs)))
        return HyperliquidOrderAck(
            True,
            202,
            "resting",
            client_order_id=_CLIENT_ORDER_ID,
        )

    adapter.place_protective_stop.side_effect = place_stop
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink(timeline),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
    )

    submission.place_protective_stop(
        position_size_signed=0.30,
        trigger_price=72.40,
    )

    assert timeline[0] == (
        "order_intent",
        {
            "operation": "protective_stop",
            "client_order_id": _CLIENT_ORDER_ID,
            "position_size_signed": 0.30,
            "trigger_price": 72.40,
        },
    )
    assert timeline[1][0] == "venue_place_stop"


def test_target_intent_precedes_authenticated_submission() -> None:
    """A required target is durably identified before the venue mutation."""
    from hypervector.live.sol_order_submission import SolOrderSubmission

    timeline: list[tuple[str, object]] = []
    adapter = Mock()

    def submit_target(**kwargs: object) -> HyperliquidOrderAck:
        timeline.append(("venue_submit_target", dict(kwargs)))
        return HyperliquidOrderAck(
            True,
            203,
            "resting",
            client_order_id=_CLIENT_ORDER_ID,
        )

    adapter.submit_target.side_effect = submit_target
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink(timeline),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
    )

    submission.place_target(position_size_signed=0.30, limit_price=74.0)

    assert timeline[0] == (
        "order_intent",
        {
            "operation": "target",
            "client_order_id": _CLIENT_ORDER_ID,
            "position_size_signed": 0.30,
            "limit_price": 74.0,
        },
    )
    assert timeline[1][0] == "venue_submit_target"


def test_close_intent_precedes_authenticated_submission() -> None:
    """A reduce-only close can be distinguished from a never-sent request."""
    from hypervector.live.sol_order_submission import SolOrderSubmission

    timeline: list[tuple[str, object]] = []
    adapter = Mock()

    def close_position(**kwargs: object) -> HyperliquidOrderAck:
        timeline.append(("venue_close_position", dict(kwargs)))
        return HyperliquidOrderAck(
            True,
            303,
            "filled",
            client_order_id=_CLIENT_ORDER_ID,
        )

    adapter.close_position.side_effect = close_position
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink(timeline),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
    )

    submission.close_position(
        position_size_signed=0.30,
        mark_price=73.0,
    )

    assert timeline[0] == (
        "order_intent",
        {
            "operation": "reduce_only_close",
            "client_order_id": _CLIENT_ORDER_ID,
            "position_size_signed": 0.30,
            "mark_price": 73.0,
        },
    )
    assert timeline[1][0] == "venue_close_position"


def test_entry_timeout_recovers_exact_committed_order_by_client_id() -> None:
    """A committed entry with a lost response is adopted without resubmission."""
    from hypervector.live.sol_order_submission import SolOrderSubmission
    from hypervector.live.sol_order_transport import SolOrderTransportError

    timeline: list[tuple[str, object]] = []
    adapter = Mock()
    adapter.submit_entry.side_effect = SolOrderTransportError(
        operation="entry",
        client_order_id=_CLIENT_ORDER_ID,
        detail="response deadline exceeded",
    )
    adapter.order_status_by_client_id.return_value = HyperliquidOrderStatus(
        101,
        "SOL",
        "filled",
        0.30,
        1_785_495_600_123,
        _CLIENT_ORDER_ID,
    )
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink(timeline),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
        recovery_attempts=3,
        recovery_delay_seconds=0.01,
        sleep_fn=lambda _: None,
    )

    ack = submission.submit_entry(
        side="long",
        requested_notional_usd=22.50,
        mark_price=73.0,
    )

    assert ack.accepted is True
    assert ack.oid == 101
    assert ack.client_order_id == _CLIENT_ORDER_ID
    assert ack.recovered_after_transport_error is True
    assert ack.venue_timestamp_ms == 1_785_495_600_123
    adapter.submit_entry.assert_called_once()
    adapter.order_status_by_client_id.assert_called_once_with(_CLIENT_ORDER_ID)


def test_entry_recovery_retries_temporarily_unknown_client_order_id() -> None:
    """Bounded read-after-write lag does not cause duplicate submission."""
    from hypervector.live.hyperliquid_sol_parsing import (
        HyperliquidOrderUnavailableError,
    )
    from hypervector.live.sol_order_submission import SolOrderSubmission
    from hypervector.live.sol_order_transport import SolOrderTransportError

    adapter = Mock()
    adapter.submit_entry.side_effect = SolOrderTransportError(
        operation="entry",
        client_order_id=_CLIENT_ORDER_ID,
        detail="response deadline exceeded",
    )
    recovered = HyperliquidOrderStatus(
        101,
        "SOL",
        "filled",
        0.30,
        1_785_495_600_123,
        _CLIENT_ORDER_ID,
    )
    adapter.order_status_by_client_id.side_effect = [
        HyperliquidOrderUnavailableError("order is not visible yet"),
        recovered,
    ]
    delays: list[float] = []
    timeline: list[tuple[str, object]] = []
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink(timeline),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
        recovery_attempts=3,
        recovery_delay_seconds=0.01,
        sleep_fn=delays.append,
    )

    ack = submission.submit_entry(
        side="long",
        requested_notional_usd=22.50,
        mark_price=73.0,
    )

    assert ack.oid == 101
    assert adapter.submit_entry.call_count == 1
    assert adapter.order_status_by_client_id.call_count == 2
    assert delays == [0.01]


def test_restart_recovers_existing_intent_without_venue_mutation() -> None:
    """Startup resolves the durable CLOID without creating a second order."""
    from hypervector.live.sol_order_submission import SolOrderSubmission

    adapter = Mock()
    adapter.order_status_by_client_id.return_value = HyperliquidOrderStatus(
        101,
        "SOL",
        "filled",
        0.30,
        1_785_495_600_123,
        _CLIENT_ORDER_ID,
    )
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink([]),
        client_order_id_fn=Mock(),
        sleep_fn=lambda _: None,
    )

    ack = submission.recover_existing_intent(
        operation="entry",
        client_order_id=_CLIENT_ORDER_ID,
    )

    assert ack.oid == 101
    assert ack.recovered_after_restart is True
    adapter.order_status_by_client_id.assert_called_once_with(_CLIENT_ORDER_ID)
    adapter.submit_entry.assert_not_called()


def test_stop_timeout_recovers_exact_resting_order_by_client_id() -> None:
    """A lost stop response adopts the exact venue-visible native protection."""
    from hypervector.live.sol_order_submission import SolOrderSubmission
    from hypervector.live.sol_order_transport import SolOrderTransportError

    adapter = Mock()
    adapter.place_protective_stop.side_effect = SolOrderTransportError(
        operation="protective_stop",
        client_order_id=_CLIENT_ORDER_ID,
        detail="response deadline exceeded",
    )
    adapter.order_status_by_client_id.return_value = HyperliquidOrderStatus(
        202,
        "SOL",
        "open",
        0.30,
        1_785_495_600_123,
        _CLIENT_ORDER_ID,
    )
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink([]),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
        sleep_fn=lambda _: None,
    )

    ack = submission.place_protective_stop(
        position_size_signed=0.30,
        trigger_price=72.40,
    )

    assert ack.accepted is True
    assert ack.oid == 202
    assert ack.recovered_after_transport_error is True
    adapter.place_protective_stop.assert_called_once()


def test_target_timeout_recovers_exact_resting_order_by_client_id() -> None:
    """A lost target response adopts its CLOID without duplicate submission."""
    from hypervector.live.sol_order_submission import SolOrderSubmission
    from hypervector.live.sol_order_transport import SolOrderTransportError

    adapter = Mock()
    adapter.submit_target.side_effect = SolOrderTransportError(
        operation="target",
        client_order_id=_CLIENT_ORDER_ID,
        detail="response deadline exceeded",
    )
    adapter.order_status_by_client_id.return_value = HyperliquidOrderStatus(
        203,
        "SOL",
        "open",
        0.30,
        1_785_495_600_123,
        _CLIENT_ORDER_ID,
    )
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink([]),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
        sleep_fn=lambda _: None,
    )

    ack = submission.place_target(position_size_signed=0.30, limit_price=74.0)

    assert ack.oid == 203
    assert ack.recovered_after_transport_error is True
    adapter.submit_target.assert_called_once()


def test_close_timeout_recovers_exact_filled_order_by_client_id() -> None:
    """A lost close response verifies the original close without resubmission."""
    from hypervector.live.sol_order_submission import SolOrderSubmission
    from hypervector.live.sol_order_transport import SolOrderTransportError

    adapter = Mock()
    adapter.close_position.side_effect = SolOrderTransportError(
        operation="reduce_only_close",
        client_order_id=_CLIENT_ORDER_ID,
        detail="response deadline exceeded",
    )
    adapter.order_status_by_client_id.return_value = HyperliquidOrderStatus(
        303,
        "SOL",
        "filled",
        0.30,
        1_785_495_600_123,
        _CLIENT_ORDER_ID,
    )
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink([]),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
        sleep_fn=lambda _: None,
    )

    ack = submission.close_position(
        position_size_signed=0.30,
        mark_price=73.0,
    )

    assert ack.accepted is True
    assert ack.oid == 303
    assert ack.recovered_after_transport_error is True
    adapter.close_position.assert_called_once()


def test_exhausted_unknown_order_fault_preserves_identity_without_resubmit() -> None:
    """Unresolved ambiguity stops at one mutation and reports the exact CLOID."""
    from hypervector.live.hyperliquid_sol_parsing import (
        HyperliquidOrderUnavailableError,
    )
    from hypervector.live.sol_order_submission import (
        SolOrderRecoveryError,
        SolOrderSubmission,
    )
    from hypervector.live.sol_order_transport import SolOrderTransportError

    adapter = Mock()
    adapter.submit_entry.side_effect = SolOrderTransportError(
        operation="entry",
        client_order_id=_CLIENT_ORDER_ID,
        detail="response deadline exceeded",
    )
    adapter.order_status_by_client_id.side_effect = HyperliquidOrderUnavailableError(
        "order is not visible yet"
    )
    delays: list[float] = []
    timeline: list[tuple[str, object]] = []
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink(timeline),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
        recovery_attempts=3,
        recovery_delay_seconds=0.01,
        sleep_fn=delays.append,
    )

    with pytest.raises(SolOrderRecoveryError) as raised:
        submission.submit_entry(
            side="long",
            requested_notional_usd=22.50,
            mark_price=73.0,
        )

    assert raised.value.operation == "entry"
    assert raised.value.client_order_id == _CLIENT_ORDER_ID
    assert adapter.submit_entry.call_count == 1
    assert adapter.order_status_by_client_id.call_count == 3
    assert delays == [0.01, 0.01]
    assert timeline[-1][0] == "fault"
    assert _CLIENT_ORDER_ID in str(timeline[-1][1])


def test_cancel_timeout_recovers_exact_oid_without_second_cancel() -> None:
    """A lost exact-cancel response is resolved through its original OID."""
    from hypervector.live.sol_order_submission import SolOrderSubmission
    from hypervector.live.sol_order_transport import SolCancelTransportError

    timeline: list[tuple[str, object]] = []
    adapter = Mock()
    adapter.cancel_order.side_effect = SolCancelTransportError(
        operation="cancel_order",
        oid=202,
        detail="response deadline exceeded",
    )
    adapter.order_status.return_value = HyperliquidOrderStatus(
        202,
        "SOL",
        "canceled",
        0.30,
        1_785_495_600_123,
    )
    submission = SolOrderSubmission(
        adapter=adapter,
        events=RecordingEventSink(timeline),
        client_order_id_fn=lambda: _CLIENT_ORDER_ID,
        sleep_fn=lambda _: None,
    )

    ack = submission.cancel_order(202)

    assert ack.accepted is True
    assert ack.oid == 202
    assert ack.status == "canceled"
    adapter.cancel_order.assert_called_once_with(202)
    adapter.order_status.assert_called_once_with(202)
    assert timeline[0] == (
        "cancel_intent",
        {"operation": "cancel_order", "oid": 202},
    )
