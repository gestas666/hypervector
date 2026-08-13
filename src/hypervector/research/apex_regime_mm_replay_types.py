"""Typed state and result records for Apex market-maker event replay."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from typing import Literal

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent
from hypervector.research.apex_regime_mm_policy import (
    ApexMMPolicyConfig,
)


ReplayEvent = L2SnapshotEvent | PublicTradeEvent
Side = Literal["buy", "sell"]
LiquiditySide = Literal["maker", "taker"]


@dataclass(frozen=True)
class FundingPoint:
    """One point-in-time hourly funding settlement rate."""

    timestamp_ms: int
    hourly_rate: float

    def __post_init__(self) -> None:
        if self.timestamp_ms < 0 or not math.isfinite(self.hourly_rate):
            raise ValueError("funding point must have a valid timestamp and rate")


@dataclass(frozen=True)
class ApexMMReplayConfig:
    """Frozen event execution and risk assumptions."""

    policy: ApexMMPolicyConfig = field(default_factory=ApexMMPolicyConfig)
    initial_equity_usd: float = 15_000.0
    maker_fee_rate: float = 0.00015
    taker_fee_rate: float = 0.00045
    submit_latency_ms: int = 50
    cancel_latency_ms: int = 50
    quote_refresh_ms: int = 1_000
    markout_horizon_ms: int = 1_000
    leverage: float = 3.0
    venue_max_leverage: float = 40.0
    cascade_trigger_bps: float = 20.0

    def __post_init__(self) -> None:
        if self.initial_equity_usd <= 0.0:
            raise ValueError("market-maker initial equity must be positive")
        for rate in (self.maker_fee_rate, self.taker_fee_rate):
            if not 0.0 <= rate < 1.0:
                raise ValueError("market-maker fee rates must be in [0, 1)")
        if not math.isclose(self.maker_fee_rate, self.policy.maker_fee_rate):
            raise ValueError("policy and replay maker fee rates must match")
        if self.submit_latency_ms < 0 or self.cancel_latency_ms < 0:
            raise ValueError("market-maker latencies must be non-negative")
        if self.quote_refresh_ms <= 0 or self.markout_horizon_ms <= 0:
            raise ValueError("refresh and markout horizons must be positive")
        if not 0.0 < self.leverage <= self.venue_max_leverage:
            raise ValueError("market-maker leverage exceeds venue specification")
        if self.cascade_trigger_bps < 0.0:
            raise ValueError("cascade trigger must be non-negative")


@dataclass(frozen=True)
class ApexMMFill:
    """One attributed simulated maker or taker fill."""

    timestamp_ms: int
    strategy_id: str
    order_role: str
    side: Side
    price: float
    quantity: float
    liquidity_side: LiquiditySide
    fee_usd: float
    markout_bps: float | None


@dataclass(frozen=True)
class ApexMMReplayResult:
    """Complete report-only market-maker execution result."""

    strategy_id: str
    execution_authority: str
    place_attempted: bool
    initial_equity_usd: float
    final_equity_usd: float
    net_pnl_usd: float
    maker_fees_usd: float
    taker_fees_usd: float
    funding_cashflow_usd: float
    maker_fill_count: int
    taker_fill_count: int
    queue_depleted_quantity: float
    final_inventory_qty: float
    maximum_inventory_notional_usd: float
    maximum_drawdown_pct: float
    minimum_liquidation_distance_pct: float | None
    liquidations: int
    fills: tuple[ApexMMFill, ...]


@dataclass
class ReplayOrder:
    """Mutable resting-order state used within a replay."""

    side: Side
    role: str
    price: float
    remaining: float
    queue_ahead: float
    active_at_ms: int
    cancel_at_ms: int | None = None


@dataclass
class ReplayFill:
    """Mutable fill state awaiting a future markout observation."""

    timestamp_ms: int
    order_role: str
    side: Side
    price: float
    quantity: float
    liquidity_side: LiquiditySide
    fee_usd: float
    markout_bps: float | None = None


@dataclass
class ReplayState:
    """Mutable accounting and execution state for one replay."""

    config: ApexMMReplayConfig
    cash: float
    inventory: float = 0.0
    average_entry: float = 0.0
    position_open_fees: float = 0.0
    position_funding: float = 0.0
    current_book: L2SnapshotEvent | None = None
    previous_mid: float | None = None
    last_quote_ms: int | None = None
    active: dict[Side, ReplayOrder] = field(default_factory=dict)
    pending: dict[Side, ReplayOrder] = field(default_factory=dict)
    fills: list[ReplayFill] = field(default_factory=list)
    mid_returns: deque[float] = field(default_factory=lambda: deque(maxlen=20))
    maker_fees: float = 0.0
    taker_fees: float = 0.0
    funding_cashflow: float = 0.0
    queue_depleted: float = 0.0
    max_inventory_notional: float = 0.0
    peak_equity: float = 0.0
    maximum_drawdown_pct: float = 0.0
    minimum_liquidation_distance_pct: float | None = None
    liquidations: int = 0
    next_funding_index: int = 0
