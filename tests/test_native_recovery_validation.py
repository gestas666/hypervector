"""Recovery rejects corrupt ownership without acquiring mutation authority."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_sol_range_onset_live_engine import _order, _runtime, _venue

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.sol_order_restart import PendingSolOrderIntent
from hypervector.live.sol_order_submission import (
    SolOrderRecoveryError,
    SolOrderSubmission,
    SolOrderSubmissionError,
)
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_state import SolLiveStateMachine
from hypervector.live.sol_range_onset_stop_restart import recover_pending_stop
from hypervector.live.sol_startup_support import _recover_intent_ack

CLIENT_ID = "0x11111111111111111111111111111111"


class StopRecoveryCase:
    """Typed production state and explicit mock mutation ports for invalid evidence."""

    def __init__(self, root: Path) -> None:
        """Create owned protecting context without constructing account clients."""
        self.config, _ = _runtime(root)
        self.events = Mock(spec=SolLiveEngineEvents)
        self.orders = Mock(spec=SolOrderSubmission)
        self.orders.recover_existing_intent.return_value = HyperliquidOrderAck(True, 202, "open")
        self.poller = Mock(spec=SolReconciliationPoller)
        self.emergency = Mock(side_effect=AssertionError("unexpected emergency mutation"))
        self.pending = PendingSolOrderIntent(
            "protective_stop", CLIENT_ID, "2026-07-31T12:00:00+00:00", {}
        )
        self.records: list[dict[str, object]] = [
            {
                "event_type": "state_transition",
                "payload": {
                    "state": "PROTECTING",
                    "entry_oid": 101,
                    "position_size_signed": 0.3,
                    "opened_at_ms": 1785495600123,
                },
            },
            {"event_type": "order_intent", "payload": {"client_order_id": CLIENT_ID}},
        ]
        self.venue = _venue(0.3, (_order(202, size=0.3, reduce_only=True, trigger=True),))

    def run(self) -> None:
        """Invoke actual stop recovery with every mutating boundary inspectable."""
        machine = SolLiveStateMachine()
        machine.begin_preflight()
        recover_pending_stop(
            config=self.config,
            events=self.events,
            machine=machine,
            orders=self.orders,
            pending=self.pending,
            records=self.records,
            venue=self.venue,
            poller=self.poller,
            emergency_flatten=self.emergency,
        )


@pytest.mark.parametrize(
    "case",
    [
        "missing_context",
        "missing_oid",
        "unaccepted",
        "missing_entry_price",
        "unowned_flat",
        "foreign_stop",
    ],
)
def test_invalid_stop_restart_fails_without_emergency_or_replacement(
    tmp_path: Path, case: str
) -> None:
    """Unknown ownership fails explicitly instead of placing, canceling or closing."""
    scenario = StopRecoveryCase(tmp_path)
    if case == "missing_context":
        scenario.records = []
    elif case == "missing_oid":
        scenario.orders.recover_existing_intent.return_value = HyperliquidOrderAck(
            True, None, "open"
        )
    elif case == "unaccepted":
        scenario.orders.recover_existing_intent.return_value = HyperliquidOrderAck(
            False, 202, "error"
        )
    elif case == "missing_entry_price":
        position = replace(scenario.venue.position, entry_price=None)
        scenario.venue = replace(
            scenario.venue, account=replace(scenario.venue.account, position=position)
        )
    elif case == "unowned_flat":
        scenario.venue = _venue(0)
    else:
        scenario.venue = replace(
            scenario.venue, open_orders=(replace(scenario.venue.open_orders[0], oid=999),)
        )
    with pytest.raises(SolLiveEngineError):
        scenario.run()
    assert scenario.events.fault.called
    scenario.emergency.assert_not_called()
    assert (
        not scenario.orders.place_target.called and not scenario.orders.place_protective_stop.called
    )
    assert not scenario.orders.close_position.called and not scenario.orders.cancel_order.called


@pytest.mark.parametrize("kind", ["lookup", "identity"])
def test_startup_lookup_errors_preserve_the_failure_boundary(kind: str) -> None:
    """An unresolved lookup propagates; invalid identity additionally records a fault."""
    events, orders = Mock(spec=SolLiveEngineEvents), Mock(spec=SolOrderSubmission)
    pending = PendingSolOrderIntent("entry", CLIENT_ID, "2026-07-31T12:00:00+00:00", {})
    error = (
        SolOrderRecoveryError(operation="entry", client_order_id=CLIENT_ID)
        if kind == "lookup"
        else SolOrderSubmissionError("identity mismatch")
    )
    orders.recover_existing_intent.side_effect = error
    with pytest.raises(SolLiveEngineError):
        _recover_intent_ack(events, orders, pending)
    assert events.fault.called == (kind == "identity")
