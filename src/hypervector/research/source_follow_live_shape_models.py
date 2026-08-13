"""Typed evidence models for the deployed BTC source-follow replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal

import pandas as pd

SourceSide = Literal["long", "short"]
SourceLiveExitReason = Literal[
    "target",
    "stop",
    "liquidation",
    "maximum_hold",
    "end_of_data",
]


@dataclass(frozen=True)
class SourceLiveShapeConfig:
    """Deployed source-follow sizing, friction, and lifecycle contract."""

    initial_equity: float = 500.0
    margin_fraction: float = 0.03
    leverage: float = 5.0
    venue_max_leverage: float = 40.0
    maximum_notional_usd: float = 25.0
    stop_bps: float = 80.0
    target_bps: float = 26.6666666667
    maximum_hold_minutes: int = 1_440
    entry_fee_rate: float = 0.00045
    target_fee_rate: float = 0.00015
    market_exit_fee_rate: float = 0.00045
    liquidation_penalty_rate: float = 0.01
    entry_slippage_bps: float = 2.0
    market_exit_slippage_bps: float = 2.0
    size_decimals: int = 5

    def __post_init__(self) -> None:
        """Reject mechanics that cannot represent the deployed BTC contract."""
        positive = (
            "initial_equity",
            "leverage",
            "venue_max_leverage",
            "maximum_notional_usd",
            "stop_bps",
            "target_bps",
        )
        for name in positive:
            _positive(float(getattr(self, name)), name)
        if not 0.0 < self.margin_fraction <= 1.0:
            raise ValueError("margin_fraction must be within (0, 1]")
        if self.leverage > self.venue_max_leverage:
            raise ValueError("leverage exceeds BTC venue maximum")
        if self.maximum_hold_minutes <= 0:
            raise ValueError("maximum_hold_minutes must be positive")
        rates = (
            "entry_fee_rate",
            "target_fee_rate",
            "market_exit_fee_rate",
            "liquidation_penalty_rate",
        )
        for name in rates:
            _rate(float(getattr(self, name)), name)
        for name in ("entry_slippage_bps", "market_exit_slippage_bps"):
            _nonnegative(float(getattr(self, name)), name)
        if not 0 <= self.size_decimals <= 18:
            raise ValueError("size_decimals must be within [0, 18]")


@dataclass(frozen=True)
class SourceLiveShapeSignal:
    """One causal entry onset from the exact current source classifier."""

    decision_time: pd.Timestamp
    side: SourceSide
    reference_price: float
    confidence: float | None = None
    signal_range_bps: float | None = None

    def __post_init__(self) -> None:
        """Validate causal time, direction, and optional classifier evidence."""
        timestamp = utc_timestamp(self.decision_time, "signal decision_time")
        object.__setattr__(self, "decision_time", timestamp)
        if self.side not in {"long", "short"}:
            raise ValueError("signal side must be long or short")
        _positive(self.reference_price, "signal reference_price")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("signal confidence must be within [0, 1]")
        if self.signal_range_bps is not None:
            _nonnegative(self.signal_range_bps, "signal_range_bps")

    @property
    def decision_time_utc(self) -> str:
        """Return the normalized decision time for immutable evidence."""
        return self.decision_time.isoformat()


@dataclass(frozen=True)
class SourceLiveShapeFunding:
    """One venue funding rate applied at its causal hourly timestamp."""

    timestamp: pd.Timestamp
    rate: float

    def __post_init__(self) -> None:
        """Normalize the timestamp and reject non-finite funding."""
        object.__setattr__(self, "timestamp", utc_timestamp(self.timestamp, "funding"))
        if not math.isfinite(self.rate):
            raise ValueError("funding rate must be finite")


@dataclass(frozen=True)
class SourceLiveShapeTrade:
    """One serialized flat-to-flat deployed-shape outcome."""

    signal_time_utc: str
    side: SourceSide
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    quantity: float
    stop_price: float
    target_price: float
    liquidation_price: float
    entry_fee_usd: float
    exit_fee_usd: float
    funding_cashflow_usd: float
    liquidation_penalty_usd: float
    net_pnl_usd: float
    exit_reason: SourceLiveExitReason
    gap_evidence_overlap: bool
    ambiguous_bar_exit: bool


@dataclass(frozen=True)
class SourceLiveShapeReport:
    """Portfolio and evidence summary for one deployed-shape replay."""

    initial_equity: float
    final_equity: float
    signal_count: int
    completed_trades: int
    wins: int
    losses: int
    targets: int
    stops: int
    liquidations: int
    maximum_holds: int
    right_censored_trades: int
    occupied_signals: int
    rejected_zero_quantity: int
    ambiguous_bar_exits: int
    gap_overlap_trades: int
    total_fees_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    drawdown_basis: str
    trades: tuple[SourceLiveShapeTrade, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible immutable report."""
        return asdict(self)


def utc_timestamp(value: object, label: str) -> pd.Timestamp:
    """Return one timezone-aware timestamp normalized to UTC."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")


def _rate(value: float, label: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value < 1.0:
        raise ValueError(f"{label} must be within [0, 1)")
