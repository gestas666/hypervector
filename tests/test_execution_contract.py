"""Typed execution-contract tests for shadow and future live ports."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from hypervector.execution import (
    AccountSnapshot,
    ExecutionPort,
    OrderCommand,
    VenueOrderEvent,
)


def entry_command() -> OrderCommand:
    """Return one valid post-only entry command."""
    return OrderCommand(
        client_order_id="hv-entry-1",
        symbol="BTC",
        side="buy",
        quantity=0.01,
        order_type="limit",
        order_role="entry",
        limit_price=64_500.0,
        post_only=True,
        reduce_only=False,
        submitted_at="2026-07-26T20:00:00+00:00",
    )


def fill_event() -> VenueOrderEvent:
    """Return one valid maker fill event."""
    return VenueOrderEvent(
        client_order_id="hv-entry-1",
        venue_order_id="1234",
        event_type="filled",
        event_at="2026-07-26T20:00:00.250000+00:00",
        last_quantity=0.01,
        cumulative_quantity=0.01,
        fill_price=64_500.0,
        fee_usd=0.09675,
        liquidity_side="maker",
        reason=None,
    )


def account_snapshot() -> AccountSnapshot:
    """Return one valid isolated account snapshot."""
    return AccountSnapshot(
        observed_at="2026-07-26T20:00:01+00:00",
        equity_usd=120.0,
        available_balance_usd=36.0,
        position_quantity=0.05209,
        position_average_price=64_500.0,
        margin_mode="isolated",
        leverage=40.0,
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
    )


def test_order_command_json_round_trip() -> None:
    command = entry_command()

    assert OrderCommand.from_json(command.to_json()) == command


@pytest.mark.parametrize(
    "overrides",
    [
        {"client_order_id": ""},
        {"symbol": " "},
        {"quantity": 0.0},
        {"quantity": float("nan")},
        {"limit_price": -1.0},
        {"submitted_at": "2026-07-26T20:00:00"},
        {"submitted_at": "2026-07-26T21:00:00+01:00"},
        {"order_type": "market", "post_only": True},
        {"order_role": "target", "reduce_only": False},
    ],
)
def test_order_command_rejects_invalid_execution_state(
    overrides: dict[str, object],
) -> None:
    payload: dict[str, object] = json.loads(entry_command().to_json())
    payload.update(overrides)

    with pytest.raises(ValueError):
        OrderCommand.from_json(json.dumps(payload))


def test_target_command_requires_reduce_only() -> None:
    target = replace(
        entry_command(),
        client_order_id="hv-target-1",
        side="sell",
        order_role="target",
        reduce_only=True,
    )

    assert OrderCommand.from_json(target.to_json()) == target


def test_venue_event_json_round_trip() -> None:
    event = fill_event()

    assert VenueOrderEvent.from_json(event.to_json()) == event


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_type": "accepted", "last_quantity": 0.01},
        {"event_type": "accepted", "fill_price": 64_500.0},
        {"event_type": "accepted", "fee_usd": 0.01},
        {"event_type": "accepted", "liquidity_side": "maker"},
        {"event_type": "filled", "liquidity_side": None},
    ],
)
def test_venue_event_rejects_success_shaped_non_fill_fields(
    overrides: dict[str, object],
) -> None:
    payload: dict[str, object] = json.loads(fill_event().to_json())
    if overrides["event_type"] == "accepted":
        payload.update(
            {
                "last_quantity": 0.0,
                "fill_price": None,
                "fee_usd": 0.0,
                "liquidity_side": None,
            }
        )
    payload.update(overrides)

    with pytest.raises(ValueError):
        VenueOrderEvent.from_json(json.dumps(payload))


@pytest.mark.parametrize(
    "overrides",
    [
        {"client_order_id": ""},
        {"venue_order_id": " "},
        {"event_at": "2026-07-26T20:00:00"},
        {"last_quantity": -0.01},
        {"cumulative_quantity": float("inf")},
        {"fill_price": 0.0},
        {"fee_usd": -0.01},
    ],
)
def test_venue_event_rejects_invalid_values(
    overrides: dict[str, object],
) -> None:
    payload: dict[str, object] = json.loads(fill_event().to_json())
    payload.update(overrides)

    with pytest.raises(ValueError):
        VenueOrderEvent.from_json(json.dumps(payload))


def test_account_snapshot_json_round_trip() -> None:
    snapshot = account_snapshot()

    assert AccountSnapshot.from_json(snapshot.to_json()) == snapshot


def test_execution_port_is_runtime_checkable() -> None:
    class StubPort:
        def submit(self, command: OrderCommand) -> VenueOrderEvent:
            return fill_event()

        def cancel(
            self,
            client_order_id: str,
            *,
            requested_at: str,
        ) -> VenueOrderEvent:
            return replace(
                fill_event(),
                client_order_id=client_order_id,
                event_type="canceled",
                event_at=requested_at,
                last_quantity=0.0,
                fill_price=None,
                fee_usd=0.0,
                liquidity_side=None,
            )

        def reconcile(self) -> tuple[VenueOrderEvent, ...]:
            return (fill_event(),)

        def account_snapshot(self) -> AccountSnapshot:
            return account_snapshot()

    assert isinstance(StubPort(), ExecutionPort)
