"""Internal state shared by Market Cipher replay modules."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayTrade,
    ReplayExitLeg,
    ReplayExitReason,
    ReplayRejection,
)
from hypervector.research.shared_portfolio_models import Direction


@dataclass(frozen=True)
class ReplayCandidate:
    """One close-known signal scheduled for its next symbol bar."""

    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_open: float
    symbol: str
    candidate: str
    direction: Direction
    score: float
    stop_anchor: float
    risk_multiplier: float
    entry_price_override: float | None = None


@dataclass
class ReplayOpenPosition:
    """Mutable lifecycle state for one isolated position."""

    candidate: ReplayCandidate
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    stop_distance_bps: float
    initial_quantity: float
    remaining_quantity: float
    initial_margin: float
    risk_budget: float
    entry_fee: float
    equity_before: float
    initial_liquidation_price: float
    bars_held: int = 0
    target_one_hit: bool = False
    target_two_hit: bool = False
    pending_exit: ReplayExitReason | None = None
    gross_pnl: float = 0.0
    fees: float = 0.0
    funding_total: float = 0.0
    funding_open_basis: float = 0.0
    liquidation_penalty: float = 0.0
    legs: list[ReplayExitLeg] = field(default_factory=list)


@dataclass
class ReplayState:
    """Mutable shared-equity state across every replayed symbol."""

    equity: float
    peak_equity: float
    maximum_drawdown_pct: float = 0.0
    maximum_concurrent_positions: int = 0
    positions: dict[str, ReplayOpenPosition] = field(default_factory=dict)
    trades: list[MarketCipherReplayTrade] = field(default_factory=list)
    rejections: list[ReplayRejection] = field(default_factory=list)
