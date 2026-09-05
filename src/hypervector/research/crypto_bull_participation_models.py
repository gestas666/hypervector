"""Typed contracts for the frozen four-crypto bull-participation replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal

CryptoBullExitReason = Literal[
    "liquidation",
    "protective_stop",
    "profit_lock",
    "trend_deterioration",
    "maximum_hold",
    "end_of_data",
]


@dataclass(frozen=True)
class CryptoBullParticipationConfig:
    """Frozen signal, risk, and friction settings for one replay."""

    symbols: tuple[str, ...] = ("BTC", "ETH", "SOL", "HYPE")
    fast_ema_hours: int = 21
    slow_ema_hours: int = 55
    minimum_ema_hours: int = 55
    entry_breadth: int = 3
    exit_breadth: int = 2
    initial_equity_usd: float = 5_000.0
    margin_fraction_per_position: float = 0.10
    leverage: float = 2.0
    maximum_positions: int = 4
    maximum_total_margin_fraction: float = 0.40
    protective_stop_bps: float = 300.0
    profit_lock_activation_bps: float = 600.0
    profit_lock_floor_bps: float = 100.0
    profit_lock_giveback_bps: float = 400.0
    maximum_hold_minutes: int = 43_200
    entry_fee_bps: float = 4.32
    exit_fee_bps: float = 4.32
    adverse_slippage_bps_per_side: float = 2.0

    def __post_init__(self) -> None:
        """Reject incomplete, non-finite, or internally unsafe settings."""
        if not self.symbols or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must be unique and non-empty")
        if any(not symbol.strip() for symbol in self.symbols):
            raise ValueError("symbols must be non-empty text")
        _positive_integer(self.fast_ema_hours, "fast EMA hours")
        _positive_integer(self.slow_ema_hours, "slow EMA hours")
        _positive_integer(self.minimum_ema_hours, "minimum EMA hours")
        if self.fast_ema_hours >= self.slow_ema_hours:
            raise ValueError("fast EMA hours must be below slow EMA hours")
        _bounded_count(self.entry_breadth, len(self.symbols), "entry breadth")
        _bounded_count(self.exit_breadth, len(self.symbols), "exit breadth")
        if self.exit_breadth > self.entry_breadth:
            raise ValueError("exit breadth must not exceed entry breadth")
        _positive(self.initial_equity_usd, "initial equity")
        _fraction(self.margin_fraction_per_position, "margin fraction")
        _positive(self.leverage, "leverage")
        _bounded_count(self.maximum_positions, len(self.symbols), "positions")
        _fraction(self.maximum_total_margin_fraction, "maximum margin fraction")
        required_margin = self.margin_fraction_per_position * self.maximum_positions
        if required_margin > self.maximum_total_margin_fraction + 1e-12:
            raise ValueError("position margins exceed the total margin fraction")
        for name in (
            "protective_stop_bps",
            "profit_lock_activation_bps",
            "profit_lock_floor_bps",
            "profit_lock_giveback_bps",
        ):
            _positive(float(getattr(self, name)), name)
        if self.profit_lock_floor_bps >= self.profit_lock_activation_bps:
            raise ValueError("profit floor must be below activation")
        _positive_integer(self.maximum_hold_minutes, "maximum hold minutes")
        _nonnegative(self.entry_fee_bps, "entry fee")
        _nonnegative(self.exit_fee_bps, "exit fee")
        _nonnegative(self.adverse_slippage_bps_per_side, "slippage")


@dataclass(frozen=True)
class CryptoBullTrade:
    """One resolved venue-costed long lifecycle."""

    symbol: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    quantity: float
    margin_usd: float
    notional_usd: float
    gross_pnl_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    slippage_cost_usd: float
    net_pnl_usd: float
    holding_minutes: int
    exit_reason: CryptoBullExitReason
    initial_stop_price: float
    final_stop_price: float
    highest_completed_hour_price: float
    equity_before_usd: float
    equity_after_usd: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe trade record."""
        return asdict(self)


@dataclass(frozen=True)
class CryptoBullPortfolioReport:
    """Aggregate shared-equity results for one partition and cost scenario."""

    initial_equity_usd: float
    final_equity_usd: float
    net_pnl_usd: float
    maximum_drawdown_pct: float
    maximum_concurrent_positions: int
    maximum_margin_fraction: float
    simultaneous_stop_wave_loss_usd: float
    turnover_usd: float
    exposure_minutes: int
    available_minutes: int
    trades: tuple[CryptoBullTrade, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe portfolio report."""
        return asdict(self)


def _bounded_count(value: int, maximum: int, label: str) -> None:
    _positive_integer(value, label)
    if value > maximum:
        raise ValueError(f"{label} exceeds the symbol count")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


def _fraction(value: float, label: str) -> None:
    _positive(value, label)
    if value > 1.0:
        raise ValueError(f"{label} must not exceed one")


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
