"""Typed contracts for report-only cross-asset residual research."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Literal

ResidualDirection = Literal["long_spread", "short_spread"]
ResidualExitReason = Literal[
    "mean_reversion",
    "residual_stop",
    "maximum_hold",
    "liquidation",
    "end_of_data",
]
PairIdentity = tuple[str, str]


def declared_residual_pairs() -> tuple[PairIdentity, ...]:
    """Return the six frozen unordered pairs in stable order."""
    return (
        ("BTC", "ETH"),
        ("BTC", "SOL"),
        ("BTC", "HYPE"),
        ("ETH", "SOL"),
        ("ETH", "HYPE"),
        ("SOL", "HYPE"),
    )


@dataclass(frozen=True)
class CrossAssetResidualConfig:
    """Frozen causal fit, signal, portfolio, and friction assumptions."""

    initial_equity: float = 15_000.0
    lookback_bars: int = 4_032
    zscore_window_bars: int = 576
    refit_interval_bars: int = 288
    entry_z: float = 2.0
    exit_z: float = 0.5
    stop_z: float = 4.0
    minimum_abs_error_correction_t: float = 1.65
    maximum_hold_bars: int = 288
    reentry_cooldown_bars: int = 1
    leverage: float = 5.0
    maximum_margin_fraction: float = 0.10
    round_trip_cost_bps_per_leg: float = 13.0
    fee_round_trip_bps_per_leg: float = 9.0
    liquidation_penalty_rate: float = 0.01
    execution_authority: str = field(default="none", init=False)

    def __post_init__(self) -> None:
        """Reject incoherent contracts before producing research evidence."""
        _positive(self.initial_equity, "initial_equity")
        _minimum_integer(self.lookback_bars, 30, "lookback_bars")
        _minimum_integer(self.zscore_window_bars, 20, "zscore_window_bars")
        _minimum_integer(self.refit_interval_bars, 1, "refit_interval_bars")
        if self.refit_interval_bars > self.lookback_bars:
            raise ValueError("refit_interval_bars must not exceed lookback_bars")
        _positive(self.exit_z, "exit_z")
        _positive(self.entry_z, "entry_z")
        _positive(self.stop_z, "stop_z")
        if not self.exit_z < self.entry_z < self.stop_z:
            raise ValueError("require exit_z < entry_z < stop_z")
        _nonnegative(
            self.minimum_abs_error_correction_t,
            "minimum_abs_error_correction_t",
        )
        _minimum_integer(self.maximum_hold_bars, 1, "maximum_hold_bars")
        _minimum_integer(self.reentry_cooldown_bars, 0, "reentry_cooldown_bars")
        _positive(self.leverage, "leverage")
        _fraction(self.maximum_margin_fraction, "maximum_margin_fraction")
        _positive(
            self.round_trip_cost_bps_per_leg,
            "round_trip_cost_bps_per_leg",
        )
        _nonnegative(
            self.fee_round_trip_bps_per_leg,
            "fee_round_trip_bps_per_leg",
        )
        if self.fee_round_trip_bps_per_leg > self.round_trip_cost_bps_per_leg:
            raise ValueError("fee cost cannot exceed all-in round-trip cost")
        _rate(self.liquidation_penalty_rate, "liquidation_penalty_rate")

    @property
    def fee_rate_per_side(self) -> float:
        """Return the declared one-way fee rate for one leg."""
        return self.fee_round_trip_bps_per_leg / 2.0 / 10_000.0

    @property
    def slippage_bps_per_side(self) -> float:
        """Return residual one-way slippage for one leg."""
        residual = self.round_trip_cost_bps_per_leg - self.fee_round_trip_bps_per_leg
        return residual / 2.0

    @property
    def gross_notional_fraction(self) -> float:
        """Return maximum gross pair notional as a fraction of equity."""
        return self.maximum_margin_fraction * self.leverage


@dataclass(frozen=True)
class ResidualSignal:
    """One causal completed-bar residual entry onset."""

    decision_time_utc: str
    left_symbol: str
    right_symbol: str
    direction: ResidualDirection
    hedge_ratio: float
    intercept: float
    residual: float
    residual_mean: float
    residual_std: float
    zscore: float
    error_correction_t: float
    fit_start_utc: str
    fit_end_utc: str
    execution_authority: str = "none"


@dataclass(frozen=True)
class ResidualTrade:
    """One atomic two-leg flat-to-flat research lifecycle."""

    left_symbol: str
    right_symbol: str
    direction: ResidualDirection
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    left_direction: str
    right_direction: str
    hedge_ratio: float
    entry_zscore: float
    exit_zscore: float
    left_entry_price: float
    right_entry_price: float
    left_exit_price: float
    right_exit_price: float
    left_quantity: float
    right_quantity: float
    isolated_margin_usd: float
    left_initial_liquidation_price: float
    right_initial_liquidation_price: float
    gross_pnl_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    liquidation_penalty_usd: float
    net_pnl_usd: float
    equity_before_usd: float
    equity_after_usd: float
    exit_reason: ResidualExitReason
    report_only: bool = True
    execution_authority: str = "none"


@dataclass(frozen=True)
class ResidualPairReport:
    """Aggregate result for one frozen pair cell."""

    left_symbol: str
    right_symbol: str
    signal_count: int
    completed_trades: int
    wins: int
    losses: int
    initial_equity: float
    final_equity: float
    gross_pnl_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    liquidation_penalties_usd: float
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    liquidations: int
    conflict_rejections: int
    trades: tuple[ResidualTrade, ...]
    limitations: tuple[str, ...]
    execution_authority: str = "none"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible complete evidence record."""
        return asdict(self)


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
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
        raise ValueError(f"{label} must not exceed one")


def _rate(value: float, label: str) -> None:
    _nonnegative(value, label)
    if value >= 1.0:
        raise ValueError(f"{label} must be below one")


def _minimum_integer(value: int, minimum: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer at least {minimum}")
