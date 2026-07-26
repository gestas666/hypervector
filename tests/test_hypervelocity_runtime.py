"""Pure Hypervelocity backend coordinator characterization tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.execution import VenueOrderEvent
from hypervector.execution.models import EventType
from hypervector.strategies.hypervelocity_runtime import (
    HypervelocityRuntimeState,
    RuntimeMarketState,
    advance_hypervelocity_runtime,
)

T0 = "2026-07-26T20:00:00+00:00"


def market(
    *,
    observed_at: str = T0,
    direction: str | None = "long",
    fresh: bool = True,
) -> RuntimeMarketState:
    """Return one pre-classified backend market observation."""
    return RuntimeMarketState(
        symbol="BTC",
        observed_at=observed_at,
        entry_direction=direction,
        entry_quantity=0.04,
        entry_limit_price=64_500.0 if direction is not None else None,
        evidence_fresh=fresh,
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=60.0,
        target_price_fraction=0.002,
        price_tick=1.0,
    )


def event(
    order_id: str,
    event_type: EventType,
    *,
    at: str = "2026-07-26T20:00:01+00:00",
    last: float = 0.0,
    cumulative: float = 0.0,
    price: float | None = None,
) -> VenueOrderEvent:
    """Return one normalized venue event for coordinator input."""
    is_fill = event_type in {"partially_filled", "filled"}
    return VenueOrderEvent(
        client_order_id=order_id,
        venue_order_id="venue-1",
        event_type=event_type,
        event_at=at,
        last_quantity=last,
        cumulative_quantity=cumulative,
        fill_price=price,
        fee_usd=(last * (price or 0.0) * 0.00015) if is_fill else 0.0,
        liquidity_side="maker" if is_fill else None,
        reason=None,
    )


def test_flat_trend_and_breakout_emit_post_only_entry_commands() -> None:
    for direction, side in (("long", "buy"), ("short", "sell")):
        decision = advance_hypervelocity_runtime(
            HypervelocityRuntimeState(),
            market(direction=direction),
        )

        assert len(decision.commands) == 1
        command = decision.commands[0]
        assert command.order_role == "entry"
        assert command.side == side
        assert command.post_only is True
        assert command.reduce_only is False


def test_range_or_uncertain_execution_evidence_never_claims_entry() -> None:
    ranged = advance_hypervelocity_runtime(
        HypervelocityRuntimeState(), market(direction=None)
    )
    uncertain = advance_hypervelocity_runtime(
        HypervelocityRuntimeState(), market(fresh=False)
    )

    assert ranged.commands == ()
    assert uncertain.commands == ()
    assert uncertain.annotations == ("execution_evidence_uncertain",)


def test_flat_no_signal_does_not_emit_repeated_execution_warning() -> None:
    decision = advance_hypervelocity_runtime(
        HypervelocityRuntimeState(),
        market(direction=None, fresh=False),
    )

    assert decision.commands == ()
    assert decision.annotations == ()


def test_partial_entry_releases_proportional_reduce_only_target() -> None:
    submitted = advance_hypervelocity_runtime(HypervelocityRuntimeState(), market())
    entry = submitted.commands[0]

    accepted = advance_hypervelocity_runtime(
        submitted.state,
        market(observed_at="2026-07-26T20:00:01+00:00"),
        (event(entry.client_order_id, "accepted"),),
    )
    partial = advance_hypervelocity_runtime(
        accepted.state,
        market(observed_at="2026-07-26T20:00:02+00:00"),
        (
            event(
                entry.client_order_id,
                "partially_filled",
                at="2026-07-26T20:00:02+00:00",
                last=0.015,
                cumulative=0.015,
                price=64_500.0,
            ),
        ),
    )

    assert partial.state.position_quantity == pytest.approx(0.015)
    assert len(partial.commands) == 1
    target = partial.commands[0]
    assert target.order_role == "target"
    assert target.quantity == pytest.approx(0.015)
    assert target.limit_price == pytest.approx(64_629.0)
    assert target.reduce_only is True


def test_open_position_holds_through_range_and_opposite_regime() -> None:
    submitted = advance_hypervelocity_runtime(HypervelocityRuntimeState(), market())
    entry = submitted.commands[0]
    filled = advance_hypervelocity_runtime(
        submitted.state,
        market(observed_at="2026-07-26T20:00:02+00:00"),
        (
            event(
                entry.client_order_id,
                "filled",
                at="2026-07-26T20:00:02+00:00",
                last=0.04,
                cumulative=0.04,
                price=64_500.0,
            ),
        ),
    )

    ranged = advance_hypervelocity_runtime(
        filled.state,
        market(observed_at="2026-07-26T20:01:00+00:00", direction=None),
    )
    opposite = advance_hypervelocity_runtime(
        ranged.state,
        market(observed_at="2026-07-26T20:02:00+00:00", direction="short"),
    )

    assert ranged.commands == ()
    assert ranged.cancellations == ()
    assert opposite.commands == ()
    assert opposite.state.position_direction == "long"


def test_target_fill_closes_then_enforces_cooldown_and_regime_reset() -> None:
    submitted = advance_hypervelocity_runtime(HypervelocityRuntimeState(), market())
    entry = submitted.commands[0]
    filled = advance_hypervelocity_runtime(
        submitted.state,
        market(observed_at="2026-07-26T20:00:02+00:00"),
        (
            event(
                entry.client_order_id,
                "filled",
                at="2026-07-26T20:00:02+00:00",
                last=0.04,
                cumulative=0.04,
                price=64_500.0,
            ),
        ),
    )
    target = filled.commands[0]
    closed = advance_hypervelocity_runtime(
        filled.state,
        market(observed_at="2026-07-26T20:00:30+00:00"),
        (
            event(
                target.client_order_id,
                "filled",
                at="2026-07-26T20:00:30+00:00",
                last=0.04,
                cumulative=0.04,
                price=64_629.0,
            ),
        ),
    )

    assert closed.state.position_quantity == 0.0
    assert closed.commands == ()
    assert closed.state.completed_trade_direction == "long"

    reset = advance_hypervelocity_runtime(
        closed.state,
        market(observed_at="2026-07-26T20:01:00+00:00", direction=None),
    )
    reentered = advance_hypervelocity_runtime(
        reset.state,
        market(observed_at="2026-07-26T20:01:31+00:00"),
    )
    assert len(reentered.commands) == 1


def test_pending_direction_change_requests_cancel_before_switching() -> None:
    submitted = advance_hypervelocity_runtime(HypervelocityRuntimeState(), market())
    entry = submitted.commands[0]

    changed = advance_hypervelocity_runtime(
        submitted.state,
        market(observed_at="2026-07-26T20:00:10+00:00", direction="short"),
    )

    assert changed.commands == ()
    assert changed.cancellations == (entry.client_order_id,)

    canceled = advance_hypervelocity_runtime(
        changed.state,
        market(observed_at="2026-07-26T20:00:11+00:00", direction="short"),
        (event(entry.client_order_id, "canceled", cumulative=0.0),),
    )
    assert len(canceled.commands) == 1
    assert canceled.commands[0].side == "sell"


def test_ttl_expiry_consumes_episode_until_regime_reset() -> None:
    submitted = advance_hypervelocity_runtime(HypervelocityRuntimeState(), market())
    entry = submitted.commands[0]
    expired = advance_hypervelocity_runtime(
        submitted.state,
        market(observed_at="2026-07-26T20:05:01+00:00"),
    )

    assert expired.cancellations == (entry.client_order_id,)
    assert expired.state.expired_entry_direction == "long"

    canceled = advance_hypervelocity_runtime(
        expired.state,
        market(observed_at="2026-07-26T20:05:02+00:00"),
        (event(entry.client_order_id, "canceled"),),
    )
    assert canceled.commands == ()

    reset = advance_hypervelocity_runtime(
        canceled.state,
        market(observed_at="2026-07-26T20:06:00+00:00", direction=None),
    )
    retry = advance_hypervelocity_runtime(
        reset.state,
        market(observed_at="2026-07-26T20:07:00+00:00"),
    )
    assert len(retry.commands) == 1


def test_event_for_unknown_order_fails_closed() -> None:
    unknown = event("unknown", "accepted")

    with pytest.raises(ValueError, match="unknown order"):
        advance_hypervelocity_runtime(HypervelocityRuntimeState(), market(), (unknown,))


def test_duplicate_partial_fill_is_idempotent() -> None:
    submitted = advance_hypervelocity_runtime(HypervelocityRuntimeState(), market())
    entry = submitted.commands[0]
    partial_event = event(
        entry.client_order_id,
        "partially_filled",
        last=0.015,
        cumulative=0.015,
        price=64_500.0,
    )
    first = advance_hypervelocity_runtime(
        submitted.state,
        market(observed_at="2026-07-26T20:00:02+00:00"),
        (partial_event,),
    )
    duplicate = advance_hypervelocity_runtime(
        first.state,
        market(observed_at="2026-07-26T20:00:03+00:00"),
        (partial_event,),
    )

    assert duplicate.state.position_quantity == pytest.approx(0.015)
    assert duplicate.commands == ()
    assert len(duplicate.state.active_targets) == 1


def test_inconsistent_cumulative_fill_fails_closed() -> None:
    submitted = advance_hypervelocity_runtime(HypervelocityRuntimeState(), market())
    entry = submitted.commands[0]
    inconsistent = event(
        entry.client_order_id,
        "partially_filled",
        last=0.01,
        cumulative=0.02,
        price=64_500.0,
    )

    with pytest.raises(ValueError, match="cumulative fill delta"):
        advance_hypervelocity_runtime(
            submitted.state,
            market(observed_at="2026-07-26T20:00:02+00:00"),
            (inconsistent,),
        )


def test_runtime_state_rejects_inconsistent_flat_position() -> None:
    with pytest.raises(ValueError, match="position_direction"):
        replace(HypervelocityRuntimeState(), position_direction="long")
