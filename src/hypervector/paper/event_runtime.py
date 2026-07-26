"""Construct the authoritative Hypervelocity event shadow runtime."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.execution import OrderCommand
from hypervector.nautilus.hyperliquid_margin import maintenance_rate_for_max_leverage
from hypervector.nautilus.hypervelocity_sim import HypervelocitySimulationConfig
from hypervector.paper.event_resume import PendingTargetResume
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
)
from hypervector.paper.maker_execution import (
    hyperliquid_price_tick,
    round_price_to_tick,
)
from hypervector.paper.nautilus_shadow import NautilusShadowExecutionPort
from hypervector.paper.resume import PendingMakerResume, ShadowPortfolioResume
from hypervector.strategies.hypervelocity_contract import HypervelocityContract
from hypervector.strategies.hypervelocity_profile import HypervelocityProfile
from hypervector.strategies.hypervelocity_runtime import (
    HypervelocityRuntimeState,
    RuntimeMarketState,
    RuntimeOrder,
)


@dataclass(frozen=True)
class _RestoredRuntime:
    state: HypervelocityRuntimeState
    commands: tuple[OrderCommand, ...]


def build_event_shadow_controller(
    *,
    profile: HypervelocityProfile,
    initial_cash_usd: float,
    observed_at: str,
    resume: ShadowPortfolioResume | None,
) -> HypervelocityShadowController:
    """Build a no-submit controller and conservatively restore durable state."""
    if profile.shadow_execution_model != "nautilus_event_v1":
        raise ValueError("event controller requires nautilus_event_v1")
    port = _event_port(profile, initial_cash_usd)
    restored = _restore_runtime(profile, resume)
    if resume is not None:
        _restore_port(port, resume, restored.state)
    return HypervelocityShadowController(
        port=port,
        initial_market=_initial_market(profile, observed_at, restored.state),
        initial_state=restored.state,
        initial_commands=restored.commands,
    )


def _event_port(
    profile: HypervelocityProfile,
    initial_cash_usd: float,
) -> NautilusShadowExecutionPort:
    simulation = HypervelocitySimulationConfig(
        submit_latency_ms=profile.execution_submit_latency_ms,
        cancel_latency_ms=profile.execution_cancel_latency_ms,
        update_latency_ms=profile.execution_update_latency_ms,
        default_leverage=int(profile.leverage),
    )
    return NautilusShadowExecutionPort(
        symbol=profile.symbol,
        initial_cash_usd=initial_cash_usd,
        simulation_config=simulation,
        maker_fee_rate=profile.maker_fee_rate,
        taker_fee_rate=profile.taker_fee_rate,
        leverage=profile.leverage,
        maintenance_rate=maintenance_rate_for_max_leverage(profile.leverage),
        max_event_age_ms=profile.execution_max_event_age_ms,
    )


def _restore_port(
    port: NautilusShadowExecutionPort,
    resume: ShadowPortfolioResume,
    state: HypervelocityRuntimeState,
) -> None:
    port.restore_position(
        quantity=resume.position_qty,
        average_price=resume.position_avg_px,
        realized_pnl=resume.realized_pnl,
        fees_paid_usd=resume.open_position_fees_usd,
        funding_net_usd=resume.open_position_funding_net_usd,
        observed_at=resume.state_asof,
    )
    port.restore_liquidation_cooldown(resume.liquidation_cooldown_until_ms)
    for order in _runtime_orders(state):
        port.restore_order(order.command, cumulative=order.cumulative_quantity)


def _initial_market(
    profile: HypervelocityProfile,
    observed_at: str,
    state: HypervelocityRuntimeState,
) -> RuntimeMarketState:
    pending = state.pending_entry
    return RuntimeMarketState(
        symbol=profile.symbol,
        observed_at=observed_at,
        entry_direction=(
            "long"
            if pending is not None and pending.command.side == "buy"
            else "short"
            if pending is not None
            else None
        ),
        entry_quantity=pending.command.quantity if pending is not None else 1.0,
        entry_limit_price=pending.command.limit_price if pending is not None else None,
        evidence_fresh=False,
        entry_ttl_seconds=profile.entry_ttl_seconds,
        reentry_cooldown_seconds=profile.reentry_cooldown_bars * 60.0,
        target_price_fraction=HypervelocityContract().target_price_fraction,
        price_tick=1.0,
    )


def _restore_runtime(
    profile: HypervelocityProfile,
    resume: ShadowPortfolioResume | None,
) -> _RestoredRuntime:
    if resume is None:
        return _RestoredRuntime(HypervelocityRuntimeState(), ())
    if resume.execution_model not in {
        "legacy_bar_through_v1",
        "nautilus_event_v1",
    }:
        raise ValueError(
            f"unsupported shadow execution model {resume.execution_model!r}"
        )
    pending, sequence = _pending_order(profile, resume, resume.next_order_sequence)
    targets, sequence = _target_orders(profile, resume, sequence)
    direction = None
    if resume.position_qty > 0.0:
        direction = "long"
    elif resume.position_qty < 0.0:
        direction = "short"
    state = HypervelocityRuntimeState(
        next_order_sequence=sequence,
        pending_entry=pending,
        active_targets=targets,
        position_direction=direction,
        position_quantity=abs(resume.position_qty),
        position_average_price=(
            resume.position_avg_px if resume.position_qty != 0.0 else None
        ),
        expired_entry_direction=resume.expired_entry_direction,
        completed_trade_direction=resume.completed_trade_direction,
        last_exit_at=resume.last_exit_at,
    )
    commands = tuple(order.command for order in _runtime_orders(state))
    return _RestoredRuntime(state, commands)


def _pending_order(
    profile: HypervelocityProfile,
    resume: ShadowPortfolioResume,
    sequence: int,
) -> tuple[RuntimeOrder | None, int]:
    pending = resume.pending_entry
    if pending is None:
        return None, sequence
    identity, sequence = _identity(pending.client_order_id, "entry", sequence)
    command = _entry_command(profile, pending, identity)
    return RuntimeOrder(command, pending.cumulative_quantity), sequence


def _entry_command(
    profile: HypervelocityProfile,
    pending: PendingMakerResume,
    identity: str,
) -> OrderCommand:
    return OrderCommand(
        client_order_id=identity,
        symbol=profile.symbol,
        side="buy" if pending.direction == "long" else "sell",
        quantity=pending.qty,
        order_type="limit",
        order_role="entry",
        limit_price=pending.limit_price,
        post_only=True,
        reduce_only=False,
        submitted_at=pending.submitted_at,
    )


def _target_orders(
    profile: HypervelocityProfile,
    resume: ShadowPortfolioResume,
    sequence: int,
) -> tuple[tuple[RuntimeOrder, ...], int]:
    targets = tuple(
        _target_command(profile, target) for target in resume.active_targets
    )
    if not targets and resume.position_qty != 0.0:
        target, sequence = _migrated_target(profile, resume, sequence)
        targets = (target,)
    orders = (
        tuple(
            RuntimeOrder(command, source.cumulative_quantity)
            for command, source in zip(targets, resume.active_targets, strict=True)
        )
        if resume.active_targets
        else tuple(RuntimeOrder(command) for command in targets)
    )
    return orders, sequence


def _target_command(
    profile: HypervelocityProfile,
    target: PendingTargetResume,
) -> OrderCommand:
    return OrderCommand(
        client_order_id=target.client_order_id,
        symbol=profile.symbol,
        side=target.side,
        quantity=target.quantity,
        order_type="limit",
        order_role="target",
        limit_price=target.limit_price,
        post_only=True,
        reduce_only=True,
        submitted_at=target.submitted_at,
    )


def _migrated_target(
    profile: HypervelocityProfile,
    resume: ShadowPortfolioResume,
    sequence: int,
) -> tuple[OrderCommand, int]:
    identity, sequence = _identity(None, "target", sequence)
    upward = resume.position_qty > 0.0
    multiplier = 1.0 + HypervelocityContract().target_price_fraction
    if not upward:
        multiplier = 1.0 - HypervelocityContract().target_price_fraction
    tick = hyperliquid_price_tick(
        resume.position_avg_px,
        size_decimals=profile.size_decimals,
    )
    limit = round_price_to_tick(
        resume.position_avg_px * multiplier,
        tick_size=tick,
        upward=upward,
    )
    return OrderCommand(
        client_order_id=identity,
        symbol=profile.symbol,
        side="sell" if upward else "buy",
        quantity=abs(resume.position_qty),
        order_type="limit",
        order_role="target",
        limit_price=limit,
        post_only=True,
        reduce_only=True,
        submitted_at=resume.state_asof,
    ), sequence


def _identity(value: str | None, role: str, sequence: int) -> tuple[str, int]:
    if value is not None:
        return value, sequence
    return f"hv-btc-{role}-{sequence:08d}", sequence + 1


def _runtime_orders(state: HypervelocityRuntimeState) -> tuple[RuntimeOrder, ...]:
    pending = (state.pending_entry,) if state.pending_entry is not None else ()
    return pending + state.active_targets
