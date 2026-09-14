"""The final-snapshot return must preserve exact ownership and failed-cleanup boundaries."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_sol_range_onset_live_engine import _order, _stop_fill, _venue

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_bracket_exit import reconcile_owned_bracket_exit
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState


def owned_snapshot() -> SolLiveSnapshot:
    """Prescribe one exact fully owned long bracket."""
    return SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=101,
        stop_oid=202,
        target_oid=303,
        target_price=101.0,
        position_size_signed=0.3,
        opened_at_ms=1000,
    )


@pytest.mark.parametrize(
    "case", ["stop_identity", "fill_evidence", "unknown_order", "cancel_rejected", "still_owned"]
)
def test_unverified_bracket_cleanup_cannot_return_a_success_snapshot(case: str) -> None:
    """Missing evidence or incomplete cleanup faults before reporting an owned exit."""
    snapshot = owned_snapshot()
    stop = _order(202, size=0.3, reduce_only=True, trigger=True)
    fill = replace(_stop_fill(oid=303, size=0.3), timestamp_ms=2000)
    venue = _venue(0.0, orders=(stop,), fills=(fill,))
    events = Mock(spec=SolLiveEngineEvents)
    orders = Mock(spec=SolOrderSubmission)
    poller = Mock(spec=SolReconciliationPoller)
    orders.cancel_order.return_value = HyperliquidOrderAck(True, 202, "canceled")
    poller.wait_for.return_value = _venue(0.0, fills=(fill,))
    if case == "stop_identity":
        snapshot = replace(snapshot, stop_oid=None)
    elif case == "fill_evidence":
        venue = replace(venue, fills=())
    elif case == "unknown_order":
        venue = replace(venue, open_orders=(stop, replace(stop, oid=999)))
    elif case == "cancel_rejected":
        orders.cancel_order.return_value = HyperliquidOrderAck(False, 202, "rejected")
    else:
        poller.wait_for.return_value = venue
    with pytest.raises(SolLiveEngineError):
        reconcile_owned_bracket_exit(
            snapshot=snapshot, venue=venue, orders=orders, events=events, poller=poller
        )
    events.confirm_owned_bracket_exit.assert_not_called()
    events.fault.assert_called_once()
    if case in {"stop_identity", "fill_evidence", "unknown_order"}:
        assert not orders.mock_calls


def test_already_clean_bracket_returns_the_exact_verified_venue_object() -> None:
    """A filled bracket with no residual order requires no cancellation."""
    fill = replace(_stop_fill(oid=303, size=0.3), timestamp_ms=2000)
    venue = _venue(0.0, fills=(fill,))
    events = Mock(spec=SolLiveEngineEvents)
    orders = Mock(spec=SolOrderSubmission)
    poller = Mock(spec=SolReconciliationPoller)
    after = replace(venue)
    poller.wait_for.return_value = after
    assert (
        reconcile_owned_bracket_exit(
            snapshot=owned_snapshot(), venue=venue, orders=orders, events=events, poller=poller
        )
        is after
    )
    assert not orders.mock_calls
    events.emit_reconciliation.assert_called_once_with(after)


@pytest.mark.parametrize("filled_oid", [202, 303])
def test_complete_owned_fill_skips_canceling_its_stale_open_order_row(filled_oid: int) -> None:
    """A full exact-order fill is already executed; only its still-unfilled sibling is canceled."""
    stop = _order(202, size=0.3, reduce_only=True, trigger=True)
    target = _order(303, size=0.3, reduce_only=True, trigger=False)
    fill = replace(_stop_fill(oid=filled_oid, size=0.3), timestamp_ms=2000)
    venue = _venue(0.0, orders=(stop, target), fills=(fill,))
    final = _venue(0.0, fills=(fill,))
    orders, events = Mock(spec=SolOrderSubmission), Mock(spec=SolLiveEngineEvents)
    poller = Mock(spec=SolReconciliationPoller)
    sibling = 303 if filled_oid == 202 else 202
    orders.cancel_order.return_value = HyperliquidOrderAck(True, sibling, "canceled")
    poller.wait_for.return_value = final
    result = reconcile_owned_bracket_exit(
        snapshot=owned_snapshot(), venue=venue, orders=orders, events=events, poller=poller
    )
    assert result is final
    orders.cancel_order.assert_called_once_with(sibling)
    events.confirm_owned_bracket_exit.assert_called_once()


def test_mixed_partial_fills_still_cancel_both_unfilled_remainders() -> None:
    """A partial fill does not prove its original order has completed or vanished."""
    stop = _order(202, size=0.3, reduce_only=True, trigger=True)
    target = _order(303, size=0.3, reduce_only=True, trigger=False)
    fills = (_stop_fill(oid=202, size=0.1), _stop_fill(oid=303, size=0.2))
    venue = _venue(0.0, orders=(stop, target), fills=fills)
    final = _venue(0.0, fills=fills)
    orders, events = Mock(spec=SolOrderSubmission), Mock(spec=SolLiveEngineEvents)
    poller = Mock(spec=SolReconciliationPoller)
    orders.cancel_order.side_effect = [
        HyperliquidOrderAck(True, 202, "canceled"),
        HyperliquidOrderAck(True, 303, "canceled"),
    ]
    poller.wait_for.return_value = final
    assert (
        reconcile_owned_bracket_exit(
            snapshot=owned_snapshot(), venue=venue, orders=orders, events=events, poller=poller
        )
        is final
    )
    assert [call.args[0] for call in orders.cancel_order.call_args_list] == [202, 303]


def test_complete_fill_does_not_hide_a_persistently_open_order() -> None:
    """Even with fill proof, final flat/open-order reconciliation remains required within bounds."""
    stop = _order(202, size=0.3, reduce_only=True, trigger=True)
    fill = _stop_fill(oid=202, size=0.3)
    venue = _venue(0.0, orders=(stop,), fills=(fill,))
    orders, events = Mock(spec=SolOrderSubmission), Mock(spec=SolLiveEngineEvents)
    poller = Mock(spec=SolReconciliationPoller)
    poller.wait_for.return_value = venue
    with pytest.raises(SolLiveEngineError, match="did not reconcile flat"):
        reconcile_owned_bracket_exit(
            snapshot=owned_snapshot(), venue=venue, orders=orders, events=events, poller=poller
        )
    orders.cancel_order.assert_not_called()
    events.confirm_owned_bracket_exit.assert_not_called()
