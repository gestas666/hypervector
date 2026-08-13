"""Pure L2 and inventory quote policy for the repaired Apex market maker."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal


CascadeSide = Literal["none", "down", "up"]


@dataclass(frozen=True)
class ApexMMPolicyConfig:
    """Cost, volatility, inventory, and freshness controls for quoting."""

    tick_size: float = 1.0
    maker_fee_rate: float = 0.00015
    minimum_edge_bps: float = 1.0
    volatility_spread_multiplier: float = 5.0
    inventory_skew_bps_at_limit: float = 10.0
    maximum_inventory_fraction: float = 0.5
    base_order_notional_usd: float = 500.0
    minimum_order_notional_usd: float = 10.0
    maximum_book_age_ms: int = 1_000
    cascade_spread_multiplier: float = 2.0
    cascade_size_multiplier: float = 0.25

    def __post_init__(self) -> None:
        if self.tick_size <= 0.0:
            raise ValueError("market-maker tick size must be positive")
        if not 0.0 <= self.maker_fee_rate < 1.0:
            raise ValueError("market-maker fee rate must be in [0, 1)")
        if self.minimum_edge_bps < 0.0:
            raise ValueError("market-maker minimum edge must be non-negative")
        if self.volatility_spread_multiplier < 0.0:
            raise ValueError("volatility spread multiplier must be non-negative")
        if self.inventory_skew_bps_at_limit < 0.0:
            raise ValueError("inventory skew must be non-negative")
        if not 0.0 < self.maximum_inventory_fraction <= 1.0:
            raise ValueError("maximum inventory fraction must be in (0, 1]")
        if self.base_order_notional_usd <= 0.0:
            raise ValueError("base order notional must be positive")
        if self.minimum_order_notional_usd <= 0.0:
            raise ValueError("minimum order notional must be positive")
        if self.base_order_notional_usd < self.minimum_order_notional_usd:
            raise ValueError("base order notional must meet the venue minimum")
        if self.maximum_book_age_ms < 0:
            raise ValueError("maximum book age must be non-negative")
        if self.cascade_spread_multiplier < 1.0:
            raise ValueError("cascade spread multiplier must be at least one")
        if not 0.0 <= self.cascade_size_multiplier <= 1.0:
            raise ValueError("cascade size multiplier must be in [0, 1]")


@dataclass(frozen=True)
class ApexMMMarketState:
    """Decision-time BBO, volatility, inventory, and cascade state."""

    best_bid: float
    best_ask: float
    best_bid_size: float
    best_ask_size: float
    volatility_bps: float
    inventory_qty: float
    equity_usd: float
    book_age_ms: int
    cascade_side: CascadeSide = "none"


@dataclass(frozen=True)
class ApexMMQuote:
    """One simultaneous post-only bid and ask recommendation."""

    active: bool
    reason: str
    fair_value: float
    bid_price: float | None
    ask_price: float | None
    bid_size: float
    ask_size: float
    full_spread_bps: float
    inventory_utilization: float


def quote_apex_regime_mm_v2(
    state: ApexMMMarketState,
    config: ApexMMPolicyConfig = ApexMMPolicyConfig(),
) -> ApexMMQuote:
    """Build cost-covering post-only quotes from real BBO depth and inventory."""
    _validate_state(state)
    midpoint = (state.best_bid + state.best_ask) / 2.0
    utilization = _inventory_utilization(state, config, midpoint)
    microprice = _microprice(state)
    skew_bps = -utilization * config.inventory_skew_bps_at_limit
    fair_value = microprice * (1.0 + skew_bps / 10_000.0)
    if state.book_age_ms > config.maximum_book_age_ms:
        return ApexMMQuote(
            False,
            "stale_book",
            fair_value,
            None,
            None,
            0.0,
            0.0,
            0.0,
            utilization,
        )
    target_spread_bps = _target_spread_bps(state, config)
    half_spread = midpoint * target_spread_bps / 20_000.0
    bid = _floor_tick(min(fair_value - half_spread, state.best_bid), config.tick_size)
    ask = _ceil_tick(max(fair_value + half_spread, state.best_ask), config.tick_size)
    if bid >= ask:
        ask = bid + config.tick_size
    bid_size, ask_size = _quote_sizes(state, config, midpoint, utilization)
    spread_bps = (ask - bid) / midpoint * 10_000.0
    return ApexMMQuote(
        True,
        "active",
        fair_value,
        bid,
        ask,
        bid_size,
        ask_size,
        spread_bps,
        utilization,
    )


def _validate_state(state: ApexMMMarketState) -> None:
    values = (
        state.best_bid,
        state.best_ask,
        state.best_bid_size,
        state.best_ask_size,
        state.volatility_bps,
        state.inventory_qty,
        state.equity_usd,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("market-maker state must be finite")
    if state.best_bid <= 0.0 or state.best_bid >= state.best_ask:
        raise ValueError("best bid must be positive and below best ask")
    if state.best_bid_size < 0.0 or state.best_ask_size < 0.0:
        raise ValueError("displayed sizes must be non-negative")
    if state.best_bid_size + state.best_ask_size <= 0.0:
        raise ValueError("displayed BBO depth must be positive")
    if state.volatility_bps < 0.0:
        raise ValueError("observed volatility must be non-negative")
    if state.equity_usd <= 0.0:
        raise ValueError("equity must be positive")
    if state.book_age_ms < 0:
        raise ValueError("book age must be non-negative")
    if state.cascade_side not in {"none", "down", "up"}:
        raise ValueError("cascade side must be none, down, or up")


def _microprice(state: ApexMMMarketState) -> float:
    total = state.best_bid_size + state.best_ask_size
    return (
        state.best_ask * state.best_bid_size + state.best_bid * state.best_ask_size
    ) / total


def _inventory_utilization(
    state: ApexMMMarketState,
    config: ApexMMPolicyConfig,
    midpoint: float,
) -> float:
    maximum_notional = state.equity_usd * config.maximum_inventory_fraction
    utilization = state.inventory_qty * midpoint / maximum_notional
    return max(-1.0, min(1.0, utilization))


def _target_spread_bps(
    state: ApexMMMarketState,
    config: ApexMMPolicyConfig,
) -> float:
    fee_floor = 2.0 * config.maker_fee_rate * 10_000.0
    spread = (
        fee_floor
        + config.minimum_edge_bps
        + state.volatility_bps * config.volatility_spread_multiplier
    )
    if state.cascade_side != "none":
        spread *= config.cascade_spread_multiplier
    return spread


def _quote_sizes(
    state: ApexMMMarketState,
    config: ApexMMPolicyConfig,
    midpoint: float,
    utilization: float,
) -> tuple[float, float]:
    base = config.base_order_notional_usd / midpoint
    bid = base * max(0.0, 1.0 - utilization)
    ask = base * max(0.0, 1.0 + utilization)
    if utilization >= 1.0:
        bid = 0.0
    if utilization <= -1.0:
        ask = 0.0
    if state.cascade_side == "down":
        bid *= config.cascade_size_multiplier
    elif state.cascade_side == "up":
        ask *= config.cascade_size_multiplier
    if 0.0 < bid * midpoint < config.minimum_order_notional_usd:
        bid = 0.0
    if 0.0 < ask * midpoint < config.minimum_order_notional_usd:
        ask = 0.0
    return round(bid, 8), round(ask, 8)


def _floor_tick(value: float, tick_size: float) -> float:
    return round(math.floor(value / tick_size + 1e-12) * tick_size, 10)


def _ceil_tick(value: float, tick_size: float) -> float:
    return round(math.ceil(value / tick_size - 1e-12) * tick_size, 10)
