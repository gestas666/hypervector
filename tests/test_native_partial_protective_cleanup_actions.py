"""Contradictory venue state must prevent residual cleanup from declaring completion."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_native_partial_protective_cleanup_evidence import pending_records
from test_native_replay_adapter import deny_external_ports
from test_asset_live_engine import _order, _venue

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.asset_order_submission import AssetOrderSubmission
from hypervector.live.asset_partial_protective_recovery import _context_snapshot
from hypervector.live.asset_protective_cleanup_actions import finish_protective_cleanup
from hypervector.live.asset_protective_cleanup_checkpoint import (
    pending_protective_cleanup,
)
from hypervector.live.asset_protective_execution_evidence import (
    ProtectiveExecutionEvidenceError,
)
from hypervector.live.asset_consistency import AssetReconciliationPoller
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_reconcile import AssetStartupReconciliationError

__all__ = ["deny_external_ports", "pending_records"]


@pytest.mark.parametrize("after_poll", [False, True])
@pytest.mark.parametrize(
    "corruption",
    [
        "position",
        "unknown",
        "duplicate_order",
        "side",
        "reduce_only",
        "new_fill",
        "changed_fill",
        "duplicate_fill",
    ],
)
def test_contradictory_venue_before_or_after_cleanup_cannot_commit_flat(
    pending_records: list[dict[str, object]], corruption: str, after_poll: bool
) -> None:
    """A completed receipt proof cannot override renewed exposure or unexplained owned fills."""
    context = pending_protective_cleanup(pending_records)
    assert context is not None and context.owner.target_oid is not None
    clean = _venue(0.0, fills=context.completed.fills)
    broken = _corrupted(clean, context.owner.target_oid, corruption)
    orders, events = Mock(spec=AssetOrderSubmission), Mock(spec=AssetLiveEngineEvents)
    poller = Mock(spec=AssetReconciliationPoller)
    poller.wait_for.return_value = broken if after_poll else clean
    with pytest.raises((AssetStartupReconciliationError, ProtectiveExecutionEvidenceError)):
        finish_protective_cleanup(
            owner=_context_snapshot(context.owner),
            completed=context.completed,
            venue=clean if after_poll else broken,
            orders=orders,
            events=events,
            poller=poller,
            resuming=True,
        )
    assert not orders.mock_calls and not events.mock_calls


def _corrupted(venue: HyperliquidReconciliationSnapshot, oid: int, kind: str) -> HyperliquidReconciliationSnapshot:
    order = _order(oid, size=0.1, reduce_only=True, trigger=True)
    if kind == "position":
        position = replace(venue.position, size_signed=0.1)
        return replace(venue, account=replace(venue.account, position=position))
    if kind == "new_fill":
        fill = replace(venue.fills[-1], trade_id=venue.fills[-1].trade_id + 99999)
        return replace(venue, fills=(*venue.fills, fill))
    if kind == "changed_fill":
        return replace(venue, fills=(*venue.fills[:-1], replace(venue.fills[-1], fee_usd=1.0)))
    if kind == "duplicate_fill":
        return replace(venue, fills=(*venue.fills, venue.fills[-1]))
    if kind == "duplicate_order":
        return replace(venue, open_orders=(order, order))
    fields = {
        "unknown": {"oid": 99999},
        "side": {"side": "B"},
        "reduce_only": {"reduce_only": False},
    }
    return replace(venue, open_orders=(replace(order, **fields[kind]),))


@pytest.mark.parametrize("failure", ["identity", "unknown_status", "cancel_rejected"])
def test_unresolved_exact_cancel_status_cannot_record_cleanup_success(
    pending_records: list[dict[str, object]], failure: str
) -> None:
    """Status ambiguity, changed ownership and rejected retries leave cleanup pending."""
    context = pending_protective_cleanup(pending_records)
    assert context is not None and context.owner.target_oid is not None
    oid = context.owner.target_oid
    venue = _venue(
        0.0,
        orders=(_order(oid, size=0.1, reduce_only=True, trigger=True),),
        fills=context.completed.fills,
    )
    orders, events = Mock(spec=AssetOrderSubmission), Mock(spec=AssetLiveEngineEvents)
    status = "unknown" if failure == "unknown_status" else "open"
    orders.recover_existing_cancel.return_value = HyperliquidOrderAck(
        False, 99999 if failure == "identity" else oid, status
    )
    orders.cancel_order.return_value = HyperliquidOrderAck(False, oid, "error", error="rejected")
    poller = Mock(spec=AssetReconciliationPoller)
    with pytest.raises(AssetStartupReconciliationError):
        finish_protective_cleanup(
            owner=_context_snapshot(context.owner),
            completed=context.completed,
            venue=venue,
            orders=orders,
            events=events,
            poller=poller,
            resuming=True,
        )
    assert orders.cancel_order.call_count == (1 if failure == "cancel_rejected" else 0)
    poller.wait_for.assert_not_called()
    events.confirm_owned_bracket_exit.assert_not_called()
    events.confirm_recorded_owned_exit.assert_not_called()
