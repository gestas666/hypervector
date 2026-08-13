"""Typed contracts for range-onset event replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal
import math

from hypervector.research.shared_portfolio_models import Direction

EventExitReason = Literal[
    "liquidation",
    "stop",
    "target",
    "opposite_signal",
    "signal",
    "max_hold",
    "end_of_data",
]
ReplayStatus = Literal["complete", "depth_failure", "evidence_failure"]
_HOUR_MS = 60 * 60 * 1_000
_DEFAULT_MAX_HOLD_MS = 48 * _HOUR_MS


@dataclass(frozen=True)
class EventReplayConfig:
    """Fixed venue, sizing, barrier, and fee assumptions."""

    initial_equity: float = 15_000.0
    margin_fraction: float = 0.10
    leverage: float = 5.0
    venue_max_leverage: float = 20.0
    stop_bps: float = 60.0
    target_bps: float | None = None
    max_hold_ms: int = _DEFAULT_MAX_HOLD_MS
    taker_fee_rate: float = 0.00045
    reentry_cooldown_ms: int = 60_000
    decision_delay_ms: int = 0

    def __post_init__(self) -> None:
        """Reject invalid risk or venue assumptions before replay."""
        _positive(self.initial_equity, "initial_equity")
        _fraction(self.margin_fraction, "margin_fraction")
        _positive(self.leverage, "leverage")
        _positive(self.venue_max_leverage, "venue_max_leverage")
        if self.leverage > self.venue_max_leverage:
            raise ValueError("leverage must not exceed venue_max_leverage")
        _positive(self.stop_bps, "stop_bps")
        if self.target_bps is not None:
            _positive(self.target_bps, "target_bps")
        _positive_integer(self.max_hold_ms, "max_hold_ms")
        _rate(self.taker_fee_rate, "taker_fee_rate")
        _nonnegative_integer(self.reentry_cooldown_ms, "reentry_cooldown_ms")
        _nonnegative_integer(self.decision_delay_ms, "decision_delay_ms")


@dataclass(frozen=True)
class EventSignal:
    """One close-known signal available at an explicit decision timestamp."""

    decision_time_ms: int
    reference_price: float
    long_entry: bool
    short_entry: bool
    long_exit: bool
    short_exit: bool

    def __post_init__(self) -> None:
        """Validate one immutable decision record."""
        _nonnegative_integer(self.decision_time_ms, "decision_time_ms")
        _positive(self.reference_price, "reference_price")
        for name in ("long_entry", "short_entry", "long_exit", "short_exit"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")


@dataclass(frozen=True)
class EventFunding:
    """One causal funding settlement with its observed reference price."""

    timestamp_ms: int
    rate: float
    reference_price: float
    reference_observed_time_ms: int | None = None
    reference_source: str = "unspecified"

    def __post_init__(self) -> None:
        """Validate one funding record."""
        _nonnegative_integer(self.timestamp_ms, "funding timestamp_ms")
        _finite(self.rate, "funding rate")
        _positive(self.reference_price, "funding reference_price")
        observed = self.reference_observed_time_ms
        if observed is not None:
            _nonnegative_integer(observed, "funding reference_observed_time_ms")
            if observed > self.timestamp_ms:
                raise ValueError("funding reference observation must be causal")
        if (
            not isinstance(self.reference_source, str)
            or not self.reference_source.strip()
        ):
            raise ValueError("funding reference_source must be non-empty")


@dataclass(frozen=True)
class EventReplayTrade:
    """One completed position using finite venue-depth fills."""

    direction: Direction
    entry_decision_time_ms: int
    entry_snapshot_time_ms: int
    exit_event_time_ms: int
    exit_snapshot_time_ms: int
    entry_price: float
    exit_price: float
    quantity: float
    stop_price: float
    liquidation_price: float
    isolated_margin_usd: float
    entry_impact_bps: float
    exit_impact_bps: float
    entry_latency_ms: int
    exit_latency_ms: int
    gross_pnl_usd: float
    entry_fee_usd: float
    exit_fee_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float
    equity_before_usd: float
    equity_after_usd: float
    exit_reason: EventExitReason


@dataclass(frozen=True)
class EventReplayReport:
    """Explicit complete or failed event-replay outcome."""

    status: ReplayStatus
    initial_equity: float
    final_equity: float
    completed_trades: int
    wins: int
    losses: int
    liquidations: int
    profit_factor: float | None
    realized_maximum_drawdown_pct: float
    mark_to_market_maximum_drawdown_pct: float | None
    mark_to_market_unobserved_trades: int | None
    total_fees_usd: float
    funding_cashflow_usd: float
    conflicting_entry_signals: int
    failure: str | None
    trades: tuple[EventReplayTrade, ...]

    def to_dict(self) -> dict[str, object]:
        """Return one JSON-safe report."""
        return asdict(self)


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be non-negative")


def _fraction(value: float, label: str) -> None:
    _positive(value, label)
    if value > 1.0:
        raise ValueError(f"{label} must not exceed 1")


def _rate(value: float, label: str) -> None:
    _nonnegative(value, label)
    if value >= 1.0:
        raise ValueError(f"{label} must be below 1")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
