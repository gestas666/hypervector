"""Ledger glue between the event shadow port and the paper ledger.

These building blocks project venue evidence into paper-ledger shapes: an L2
event into a book snapshot, order transitions into stable ledger actions and
the fresh-BBO maximum-hold exit into its fill identity and no-submit intent.
"""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.execution import OrderCommand, VenueOrderEvent
from hypervector.paper.event_book_projection import book_snapshot_from_event
from hypervector.paper.maximum_hold_execution import (
    MAXIMUM_HOLD_FILL_MODEL,
    FreshBboTakerFillModel,
    maximum_hold_order_intent,
)
from hypervector.paper.shadow_order_telemetry import order_action, timestamp

_AT = "2026-07-25T12:00:00.250000+00:00"


def _command(role: str) -> OrderCommand:
    entry = role == "entry"
    return OrderCommand(
        client_order_id=f"{role}-1",
        symbol="BTC",
        side="buy" if entry else "sell",
        quantity=0.5,
        order_type="limit" if entry else "market",
        order_role=role,  # type: ignore[arg-type]
        limit_price=100.0 if entry else None,
        post_only=entry,
        reduce_only=not entry,
        submitted_at=_AT,
    )


def _event(event_type: str, client_order_id: str) -> VenueOrderEvent:
    filled = event_type == "filled"
    return VenueOrderEvent(
        client_order_id=client_order_id,
        venue_order_id="v-1",
        event_type=event_type,  # type: ignore[arg-type]
        event_at=_AT,
        last_quantity=0.5 if filled else 0.0,
        cumulative_quantity=0.5 if filled else 0.0,
        fill_price=101.0 if filled else None,
        fee_usd=0.02 if filled else 0.0,
        liquidity_side="taker" if filled else None,
        reason=None,
    )


def test_l2_event_projects_into_a_book_snapshot_with_its_timestamps() -> None:
    event = L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=1_785_000_000_000,
        received_ts_ns=1_785_000_000_250_000_000,
        bids=(BookLevel(99.0, 2.0, 3), BookLevel(98.5, 1.0, 1)),
        asks=(BookLevel(101.0, 1.5, 2),),
    )

    snapshot = book_snapshot_from_event(event)

    assert snapshot.symbol == "BTC"
    assert snapshot.best_bid() == 99.0 and snapshot.best_ask() == 101.0
    assert snapshot.ts_exchange_ms == 1_785_000_000_000.0
    assert snapshot.ts_recv_ms == pytest.approx(1_785_000_000_250.0)
    assert snapshot.source == event.source


@pytest.mark.parametrize(
    ("role", "event_type", "action"),
    [
        ("entry", "submitted", "submit_entry"),
        ("entry", "canceled", "cancel_entry"),
        ("entry", "expired", "cancel_entry"),
        ("exit", "filled", "filled_exit"),
    ],
)
def test_order_transitions_map_to_stable_ledger_actions(
    role: str, event_type: str, action: str
) -> None:
    command = _command(role)
    assert order_action(command, _event(event_type, command.client_order_id)) == action


def test_maximum_hold_exit_fills_at_the_proven_bbo_as_a_market_ioc() -> None:
    fill = FreshBboTakerFillModel().fill(
        side="sell", qty=0.5, mark_px=101.0, book=None, slippage_bps=5.0
    )
    assert (fill.fill_px, fill.fill_qty, fill.shortfall_qty) == (101.0, 0.5, 0.0)
    assert fill.fill_model_id == MAXIMUM_HOLD_FILL_MODEL

    command = _command("exit")
    intent = maximum_hold_order_intent(command, _event("filled", command.client_order_id))
    assert (intent["order_type"], intent["time_in_force"]) == ("market", "ioc")
    assert intent["reduce_only"] is True and intent["submit_enabled"] is False
    assert intent["client_ts_ms"] == pytest.approx(timestamp(_AT).timestamp() * 1_000)
    assert timestamp(_AT) == pd.Timestamp(_AT)
