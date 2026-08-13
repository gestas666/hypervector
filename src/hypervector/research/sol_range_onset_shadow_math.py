"""Pure calculations for the SOL range-onset shadow lifecycle."""

from __future__ import annotations

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.research.market_depth_fill import (
    DepthLevel,
    MarketDepthFill,
    walk_market_order,
)
from hypervector.research.range_onset_event_models import EventReplayConfig, EventSignal
from hypervector.research.range_onset_event_risk import EventRiskPosition
from hypervector.research.shared_portfolio_models import Direction
from hypervector.research.sol_range_onset_shadow_models import (
    SolShadowConfig,
    SolShadowPosition,
)

HOUR_MS = 60 * 60 * 1_000


def depth_fill(
    event: L2SnapshotEvent,
    direction: Direction,
    quantity: float,
    *,
    entering: bool,
) -> MarketDepthFill:
    """Walk the appropriate visible book side for an entry or exit."""
    buy = (direction == "long") == entering
    levels = event.asks if buy else event.bids
    depth = tuple(DepthLevel(level.price, level.size) for level in levels)
    return walk_market_order(depth, side="buy" if buy else "sell", quantity=quantity)


def stop_price(direction: Direction, entry: float, stop_bps: float) -> float:
    """Return the directional hard-stop price."""
    fraction = stop_bps / 10_000.0
    return entry * (1.0 - fraction if direction == "long" else 1.0 + fraction)


def barrier_crossed(direction: Direction, mark_price: float, barrier: float) -> bool:
    """Return whether a directional mark-price barrier has been crossed."""
    return mark_price <= barrier if direction == "long" else mark_price >= barrier


def desired_direction(decision: EventSignal) -> Direction | None:
    """Return the unambiguous requested entry direction, if one exists."""
    if decision.long_entry == decision.short_entry:
        return None
    return "long" if decision.long_entry else "short"


def risk_position(position: SolShadowPosition) -> EventRiskPosition:
    """Project a live shadow position into the shared liquidation model."""
    return EventRiskPosition(
        position.direction,
        position.quantity,
        position.entry_price,
        position.margin_usd,
        position.entry_fee_usd,
        position.entry_time_ms,
        position.stop_price,
    )


def hour_floor(timestamp_ms: int) -> int:
    """Floor a millisecond timestamp to its funding hour."""
    return timestamp_ms - timestamp_ms % HOUR_MS


def event_config(config: SolShadowConfig) -> EventReplayConfig:
    """Project the shadow configuration into the shared risk configuration."""
    return EventReplayConfig(
        initial_equity=config.initial_shared_equity_usd,
        margin_fraction=config.margin_fraction,
        leverage=config.leverage,
        venue_max_leverage=config.venue_max_leverage,
        stop_bps=config.stop_bps,
        max_hold_ms=config.max_hold_ms,
        taker_fee_rate=config.taker_fee_rate,
    )
