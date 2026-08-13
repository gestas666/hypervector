"""Typed contracts for report-only HYPE breakout exit research."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

HypeSide = Literal["long", "short"]
HypeMaximumHoldPolicy = Literal["fixed", "extend_while_regime_supported"]
HypeExitReason = Literal[
    "protective_stop",
    "profit_protection",
    "breakout_invalidation",
    "structural_reversal",
    "momentum_reversal_5m",
    "maximum_hold",
    "hard_maximum_hold",
    "end_of_data",
]


@dataclass(frozen=True)
class HypeExitPolicy:
    """One predeclared causal exit mechanism around the common safety exits."""

    policy_id: str
    exit_on_invalidation: bool = False
    exit_on_reversal: bool = False
    exit_on_5m_rsi_reversal: bool = False
    profit_activation_bps: float | None = None
    profit_floor_bps: float | None = None
    trailing_giveback_bps: float | None = None
    reentry_requires_structural_reset: bool = False

    def __post_init__(self) -> None:
        """Require a stable non-empty policy identity."""
        if not self.policy_id.strip():
            raise ValueError("HYPE exit policy_id must be non-empty")
        values = (
            self.profit_activation_bps,
            self.profit_floor_bps,
            self.trailing_giveback_bps,
        )
        if all(value is None for value in values):
            if self.reentry_requires_structural_reset:
                raise ValueError("HYPE reentry reset requires profit protection")
            return
        if any(value is None for value in values):
            raise ValueError("HYPE profit protection requires a complete triplet")
        activation, floor, giveback = values
        if activation is None or floor is None or giveback is None:
            raise RuntimeError("validated HYPE profit protection is incomplete")
        _positive(activation, "profit activation")
        _nonnegative(floor, "profit protection floor")
        _positive(giveback, "profit protection giveback")
        if floor >= activation:
            raise ValueError("HYPE profit protection floor must be below activation")


@dataclass(frozen=True)
class HypeExitReplayConfig:
    """Frozen unit-notional execution assumptions for HYPE exit comparison."""

    stop_bps: float = 80.0
    maximum_hold_minutes: int = 480
    maximum_hold_policy: HypeMaximumHoldPolicy = "fixed"
    hard_maximum_hold_minutes: int | None = None
    fee_bps_per_side: float = 4.5
    slippage_bps_per_side: float = 2.0

    def __post_init__(self) -> None:
        """Reject non-finite or non-positive economic assumptions."""
        _positive(self.stop_bps, "stop_bps")
        _positive_integer(self.maximum_hold_minutes, "maximum_hold_minutes")
        if self.maximum_hold_policy not in {"fixed", "extend_while_regime_supported"}:
            raise ValueError("unsupported HYPE maximum hold policy")
        if self.maximum_hold_policy == "fixed":
            if self.hard_maximum_hold_minutes is not None:
                raise ValueError("fixed HYPE maximum hold cannot have a hard extension")
        elif (
            self.hard_maximum_hold_minutes is None
            or self.hard_maximum_hold_minutes <= self.maximum_hold_minutes
        ):
            raise ValueError("HYPE extension requires a later hard maximum hold")
        _nonnegative(self.fee_bps_per_side, "fee_bps_per_side")
        _nonnegative(self.slippage_bps_per_side, "slippage_bps_per_side")


@dataclass(frozen=True)
class HypeExitTrade:
    """One serialized HYPE breakout lifecycle measured on initial notional."""

    side: HypeSide
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    stop_price: float
    gross_return_bps: float
    fee_bps: float
    funding_bps: float
    net_return_bps: float
    hold_minutes: int
    maximum_favorable_excursion_bps: float
    maximum_adverse_excursion_bps: float
    exit_reason: HypeExitReason


@dataclass(frozen=True)
class HypeExitReplayReport:
    """Economic summary for one exit policy with no execution authority."""

    policy_id: str
    completed_trades: int
    wins: int
    losses: int
    net_return_bps: float
    gross_profit_bps: float
    gross_loss_bps: float
    profit_factor: float | None
    maximum_drawdown_bps: float
    total_fee_bps: float
    funding_bps: float
    occupied_signals: int
    exit_reasons: dict[str, int]
    monthly_net_bps: dict[str, float]
    trades: tuple[HypeExitTrade, ...]
    execution_authority: str = "none"
    report_only: bool = True
    reset_blocked_signals: int = 0


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
