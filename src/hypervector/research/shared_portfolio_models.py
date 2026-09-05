"""Typed contracts for causal shared-portfolio strategy screening."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

from hypervector.cohort_profit_lock_policy import ProfitLockPolicy, policy_declaration
from hypervector.research.shared_portfolio_completed_peak_lock import (
    CompletedBarPeakLockPolicy,
)

Direction = Literal["long", "short"]
ExitReason = Literal[
    "target",
    "stop",
    "liquidation",
    "signal",
    "opposite_signal",
    "profit_lock",
    "max_hold",
    "data_gap",
    "end_of_data",
]


@dataclass(frozen=True)
class SharedPortfolioConfig:
    """Execution and isolated-risk assumptions for one shared portfolio."""

    symbol: str = "BTC"
    initial_equity: float = 15_000.0
    margin_fraction: float = 0.10
    leverage: float = 10.0
    venue_max_leverage: float = 40.0
    maximum_notional_usd: float | None = None
    risk_fraction_per_position: float | None = None
    target_margin_pct: float | None = None
    target_r_multiple: float | None = None
    stop_margin_pct: float | None = None
    minimum_stop_distance_bps: float | None = None
    maximum_stop_distance_bps: float | None = None
    entry_fee_rate: float = 0.00045
    target_fee_rate: float = 0.00015
    market_exit_fee_rate: float = 0.00045
    liquidation_fee_rate: float = 0.00045
    entry_slippage_bps: float = 2.0
    market_exit_slippage_bps: float = 2.0
    liquidation_slippage_bps: float = 0.0
    max_hold_bars: int | None = None
    max_hold_seconds: int | None = None
    reentry_cooldown_bars: int = 1
    same_direction_reentry_requires_reset: bool = False
    close_on_opposite_signal: bool = True
    reverse_on_opposite_signal: bool = False
    funding_column: str = "funding_rate"
    open_bid_column: str | None = None
    open_ask_column: str | None = None
    close_bid_column: str | None = None
    close_ask_column: str | None = None
    risk_high_column: str = "high"
    risk_low_column: str = "low"
    entry_risk_high_column: str | None = None
    entry_risk_low_column: str | None = None
    signal_exit_max_age_bars: int | None = None
    signal_exit_max_mfe_bps: float | None = None
    signal_exit_min_adverse_bps: float | None = None
    completed_bar_profit_lock: ProfitLockPolicy | None = None
    completed_bar_peak_lock: CompletedBarPeakLockPolicy | None = None

    def __post_init__(self) -> None:
        """Reject unsafe, non-finite, or venue-incompatible assumptions."""
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        _positive(self.initial_equity, "initial_equity")
        _fraction(self.margin_fraction, "margin_fraction")
        _positive(self.leverage, "leverage")
        _positive(self.venue_max_leverage, "venue_max_leverage")
        if self.leverage > self.venue_max_leverage:
            raise ValueError("leverage must not exceed venue_max_leverage")
        _optional_positive(self.maximum_notional_usd, "maximum_notional_usd")
        if self.risk_fraction_per_position is not None:
            _fraction(
                self.risk_fraction_per_position,
                "risk_fraction_per_position",
            )
        _optional_positive(self.target_margin_pct, "target_margin_pct")
        _optional_positive(self.target_r_multiple, "target_r_multiple")
        _optional_positive(self.stop_margin_pct, "stop_margin_pct")
        _optional_positive(
            self.minimum_stop_distance_bps,
            "minimum_stop_distance_bps",
        )
        _optional_positive(
            self.maximum_stop_distance_bps,
            "maximum_stop_distance_bps",
        )
        if self.target_margin_pct is not None and self.target_r_multiple is not None:
            raise ValueError("target_margin_pct and target_r_multiple are exclusive")
        if (
            self.minimum_stop_distance_bps is not None
            and self.maximum_stop_distance_bps is not None
            and self.minimum_stop_distance_bps > self.maximum_stop_distance_bps
        ):
            raise ValueError(
                "minimum_stop_distance_bps must not exceed maximum_stop_distance_bps"
            )
        for name in _FEE_FIELDS:
            _rate(float(getattr(self, name)), name)
        for name in _SLIPPAGE_FIELDS:
            _nonnegative(float(getattr(self, name)), name)
        _optional_positive_integer(self.max_hold_bars, "max_hold_bars")
        _optional_positive_integer(self.max_hold_seconds, "max_hold_seconds")
        _nonnegative_integer(self.reentry_cooldown_bars, "reentry_cooldown_bars")
        if self.reverse_on_opposite_signal and not self.close_on_opposite_signal:
            raise ValueError("reversal requires close_on_opposite_signal")
        if not self.funding_column.strip():
            raise ValueError("funding_column must be non-empty")
        _optional_column_pair(
            self.open_bid_column,
            self.open_ask_column,
            "open bid/ask",
        )
        _optional_column_pair(
            self.close_bid_column,
            self.close_ask_column,
            "close bid/ask",
        )
        if not self.risk_high_column.strip() or not self.risk_low_column.strip():
            raise ValueError("risk high/low columns must be non-empty")
        _optional_column_pair(
            self.entry_risk_high_column,
            self.entry_risk_low_column,
            "entry risk high/low",
        )
        _optional_positive_integer(
            self.signal_exit_max_age_bars,
            "signal_exit_max_age_bars",
        )
        _optional_positive(
            self.signal_exit_max_mfe_bps,
            "signal_exit_max_mfe_bps",
        )
        _optional_positive(
            self.signal_exit_min_adverse_bps,
            "signal_exit_min_adverse_bps",
        )
        _conditional_exit_fields(self)
        if self.completed_bar_profit_lock is not None:
            policy_declaration(self.completed_bar_profit_lock)


@dataclass(frozen=True)
class SharedPortfolioTrade:
    """One completed trade from the chronological shared event stream."""

    signal_name: str
    direction: Direction
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    signal_position: int
    entry_position: int
    exit_position: int
    entry_price: float
    exit_price: float
    target_price: float | None
    stop_price: float | None
    liquidation_price: float
    quantity: float
    margin_usd: float
    notional_usd: float
    leverage: float
    gross_pnl_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float
    equity_before_usd: float
    equity_after_usd: float
    exit_reason: ExitReason
    same_bar_ambiguous: bool


@dataclass(frozen=True)
class SharedPortfolioReport:
    """Aggregate diagnostics produced from exactly one funded portfolio."""

    initial_equity: float
    final_equity: float
    net_pnl_usd: float
    return_pct: float
    maximum_drawdown_pct: float
    completed_trades: int
    wins: int
    losses: int
    gross_profit_usd: float
    gross_loss_usd: float
    profit_factor: float | None
    liquidations: int
    total_fees_usd: float
    funding_cashflow_usd: float
    conflicting_entry_signals: int
    maximum_concurrent_positions: int
    forced_end_exits: int
    barrier_invalidated_entries: int
    insolvent: bool
    monthly_net_pnl_usd: dict[str, float]
    limitations: tuple[str, ...]
    trades: tuple[SharedPortfolioTrade, ...]
    gap_expired_entries: int = 0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation for immutable reports."""
        return asdict(self)


_FEE_FIELDS = (
    "entry_fee_rate",
    "target_fee_rate",
    "market_exit_fee_rate",
    "liquidation_fee_rate",
)
_SLIPPAGE_FIELDS = (
    "entry_slippage_bps",
    "market_exit_slippage_bps",
    "liquidation_slippage_bps",
)


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _positive(value: float, label: str) -> None:
    _finite(float(value), label)
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


def _optional_positive(value: float | None, label: str) -> None:
    if value is not None:
        _positive(value, label)


def _optional_positive_integer(value: int | None, label: str) -> None:
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _optional_column_pair(
    bid_column: str | None,
    ask_column: str | None,
    label: str,
) -> None:
    if (bid_column is None) != (ask_column is None):
        raise ValueError(f"{label} columns must be configured together")
    if bid_column is not None and (not bid_column.strip() or not ask_column.strip()):
        raise ValueError(f"{label} columns must be non-empty")


def _conditional_exit_fields(config: SharedPortfolioConfig) -> None:
    fields = (
        config.signal_exit_max_age_bars,
        config.signal_exit_max_mfe_bps,
        config.signal_exit_min_adverse_bps,
    )
    if any(value is None for value in fields) and not all(
        value is None for value in fields
    ):
        raise ValueError("conditional signal-exit fields must be configured together")
