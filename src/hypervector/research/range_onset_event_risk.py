"""Funding-aware stop and isolated-liquidation ordering for event replay."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.research.range_onset_event_models import (
    EventFunding,
    EventReplayConfig,
)
from hypervector.research.shared_portfolio_models import Direction

BarrierCrossing = Callable[[Direction, float, int, int], int | None]
RiskExitReason = Literal["liquidation", "stop"]


@dataclass(frozen=True)
class EventRiskPosition:
    """Position terms needed to evaluate adverse venue boundaries."""

    direction: Direction
    quantity: float
    entry_price: float
    isolated_margin_usd: float
    entry_fee_usd: float
    entry_time_ms: int
    stop_price: float


@dataclass(frozen=True)
class EventRiskCrossing:
    """First adverse barrier crossing and its conservative outcome."""

    event_time_ms: int
    reason: RiskExitReason


def first_risk_crossing(
    position: EventRiskPosition,
    funding: Sequence[EventFunding],
    config: EventReplayConfig,
    crossing_source: BarrierCrossing,
    end_time_ms: int,
) -> EventRiskCrossing | None:
    """Return the first stop or funding-adjusted liquidation crossing."""
    stop_time = crossing_source(
        position.direction,
        position.stop_price,
        position.entry_time_ms,
        end_time_ms,
    )
    liquidation_end_ms = end_time_ms if stop_time is None else stop_time + 1
    liquidation_time = _first_liquidation_crossing(
        position,
        funding,
        config,
        crossing_source,
        liquidation_end_ms,
    )
    if liquidation_time is not None and (
        stop_time is None or liquidation_time <= stop_time
    ):
        return EventRiskCrossing(liquidation_time, "liquidation")
    return None if stop_time is None else EventRiskCrossing(stop_time, "stop")


def funding_cashflow(
    position: EventRiskPosition,
    event: EventFunding,
) -> float:
    """Return signed position cashflow for one funding settlement."""
    sign = 1.0 if position.direction == "long" else -1.0
    return -sign * position.quantity * event.reference_price * event.rate


def liquidation_price(
    position: EventRiskPosition,
    config: EventReplayConfig,
    funding_cash: float,
) -> float:
    """Return the isolated liquidation boundary after signed funding."""
    margin = IsolatedMarginPosition(
        symbol="event_replay",
        side=position.direction,
        quantity=position.quantity,
        entry_price=position.entry_price,
        isolated_margin=position.isolated_margin_usd,
        maintenance_rate=maintenance_rate_for_max_leverage(config.venue_max_leverage),
        fees_paid_usd=position.entry_fee_usd,
        funding_net_usd=funding_cash,
    )
    return margin.liquidation_price()


def _first_liquidation_crossing(
    position: EventRiskPosition,
    funding: Sequence[EventFunding],
    config: EventReplayConfig,
    crossing_source: BarrierCrossing,
    end_time_ms: int,
) -> int | None:
    cursor_ms = position.entry_time_ms
    funding_cash = 0.0
    for event in funding:
        if not position.entry_time_ms <= event.timestamp_ms < end_time_ms:
            continue
        crossing = _liquidation_crossing(
            position,
            config,
            crossing_source,
            funding_cash,
            cursor_ms,
            event.timestamp_ms,
        )
        if crossing is not None:
            return crossing
        funding_cash += funding_cashflow(position, event)
        cursor_ms = event.timestamp_ms
    return _liquidation_crossing(
        position,
        config,
        crossing_source,
        funding_cash,
        cursor_ms,
        end_time_ms,
    )


def _liquidation_crossing(
    position: EventRiskPosition,
    config: EventReplayConfig,
    crossing_source: BarrierCrossing,
    funding_cash: float,
    start_time_ms: int,
    end_time_ms: int,
) -> int | None:
    if start_time_ms >= end_time_ms:
        return None
    boundary = liquidation_price(position, config, funding_cash)
    return crossing_source(
        position.direction,
        boundary,
        start_time_ms,
        end_time_ms,
    )
