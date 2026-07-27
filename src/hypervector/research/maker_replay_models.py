"""Typed state and report contracts for causal maker replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import pandas as pd

Direction = Literal["long", "short"]
FillRule = Literal["touch", "through", "trade-through"]
LifecycleStatus = Literal["pending", "expired", "canceled", "open", "target_completed"]


@dataclass(frozen=True)
class MakerReplayConfig:
    """Explicit maker-replay assumptions that remain reportable and tunable."""

    initial_equity: float = 10_000.0
    maker_fee_rate: float = 0.00015
    fill_rule: FillRule = "through"
    tick_size: float = 1.0
    entry_ttl_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.initial_equity <= 0.0:
            raise ValueError("initial_equity must be positive")
        if self.maker_fee_rate < 0.0:
            raise ValueError("maker_fee_rate must be non-negative")
        if self.fill_rule not in ("touch", "through", "trade-through"):
            raise ValueError("fill_rule must be touch|through|trade-through")
        if self.tick_size <= 0.0:
            raise ValueError("tick_size must be positive")
        if self.entry_ttl_seconds <= 0.0:
            raise ValueError("entry_ttl_seconds must be positive")


@dataclass(frozen=True)
class MakerReplayTrade:
    """One completed maker-to-maker trade reconstructed from market evidence."""

    direction: Direction
    signal_time_utc: str
    submitted_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    quantity: float
    margin: float
    notional: float
    gross_pnl: float
    fees: float
    net_pnl: float
    entry_wait_seconds: float
    hold_seconds: float


@dataclass(frozen=True)
class MakerReplayLifecycle:
    """Final observed state of one causally submitted maker entry."""

    lifecycle_id: int
    direction: Direction
    signal_time_utc: str
    submitted_time_utc: str
    entry_time_utc: str | None
    outcome_time_utc: str | None
    status: LifecycleStatus
    entry_price: float | None
    exit_price: float | None
    quantity: float | None
    fees: float | None
    net_pnl: float | None


@dataclass(frozen=True)
class MakerReplayReport:
    """Complete maker replay including unresolved order uncertainty."""

    fill_rule: FillRule
    snapshots: int
    market_trade_prints: int
    submitted_entries: int
    entry_fills: int
    expired_entries: int
    canceled_entries: int
    pending_orders: int
    completed_trades: int
    open_positions: int
    initial_equity: float
    final_equity: float
    submission_times_utc: tuple[str, ...]
    trades: tuple[MakerReplayTrade, ...]
    lifecycles: tuple[MakerReplayLifecycle, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe replay report."""
        return asdict(self)


@dataclass
class PendingEntry:
    """Mutable pending maker-entry state carried across evidence chunks."""

    lifecycle_id: int
    direction: Direction
    signal_time: pd.Timestamp
    submitted_time: pd.Timestamp
    limit_price: float
    trade_through_volume: float = 0.0


@dataclass
class OpenPosition:
    """Mutable open position carried until its fixed target is evidenced."""

    lifecycle_id: int
    direction: Direction
    signal_time: pd.Timestamp
    submitted_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_price: float
    quantity: float
    margin: float
    notional: float
    target_price: float
    exit_trade_through_volume: float = 0.0


@dataclass
class ReplayState:
    """Complete mutable maker-replay state for one continuous window."""

    equity: float
    pending: PendingEntry | None = None
    position: OpenPosition | None = None
    expired_direction: Direction | None = None
    last_signal: pd.Timestamp | None = None
    submitted: int = 0
    entry_fills: int = 0
    expired: int = 0
    canceled: int = 0
    submissions: list[str] = field(default_factory=list)
    trades: list[MakerReplayTrade] = field(default_factory=list)
    lifecycles: list[MakerReplayLifecycle] = field(default_factory=list)
