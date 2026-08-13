"""Friction-aware independent-asset screen for Swing/HA signals."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from itertools import product
import math

import pandas as pd

from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_EMA_PAIRS = ((7, 21), (9, 21), (9, 26), (12, 26), (20, 50), (50, 200))
_PIVOT_LENGTHS = (3, 5, 8)
_ENTRY_MODES = ("state", "onset")
_EXIT_MODES = ("ha_flip", "alignment_loss")
_OB_PERIODS = (3, 5)
_OB_MOVES = (0.0, 0.25, 0.50)


@dataclass(frozen=True)
class SwingHaScreenConfig:
    """Frozen capital and realistic market-friction assumptions."""

    initial_equity: float = 15_000.0
    margin_fraction: float = 0.10
    leverage: float = 5.0
    fee_rate_per_side: float = 0.00045
    slippage_bps_per_side: float = 2.0
    reentry_cooldown_bars: int = 1

    def __post_init__(self) -> None:
        """Reject invalid economic assumptions."""
        values = (
            self.initial_equity,
            self.margin_fraction,
            self.leverage,
            self.fee_rate_per_side,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("Swing/HA economic assumptions must be positive")
        if self.margin_fraction > 1.0:
            raise ValueError("Swing/HA margin fraction cannot exceed one")
        if not math.isfinite(self.slippage_bps_per_side):
            raise ValueError("Swing/HA slippage must be finite")
        if self.slippage_bps_per_side < 0.0:
            raise ValueError("Swing/HA slippage must be non-negative")

    def portfolio_config(
        self, *, symbol: str, venue_max_leverage: float
    ) -> SharedPortfolioConfig:
        """Return the shared simulator configuration without hidden exits."""
        return SharedPortfolioConfig(
            symbol=symbol,
            initial_equity=self.initial_equity,
            margin_fraction=self.margin_fraction,
            leverage=self.leverage,
            venue_max_leverage=venue_max_leverage,
            entry_fee_rate=self.fee_rate_per_side,
            target_fee_rate=self.fee_rate_per_side,
            market_exit_fee_rate=self.fee_rate_per_side,
            liquidation_fee_rate=self.fee_rate_per_side,
            entry_slippage_bps=self.slippage_bps_per_side,
            market_exit_slippage_bps=self.slippage_bps_per_side,
            reentry_cooldown_bars=self.reentry_cooldown_bars,
        )


@dataclass(frozen=True)
class SwingHaScreenCell:
    """One complete strategy configuration and asset result."""

    symbol: str
    signal_config: dict[str, object]
    completed_trades: int
    wins: int
    losses: int
    net_pnl_usd: float
    return_pct: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    liquidations: int
    total_fees_usd: float
    funding_cashflow_usd: float
    direction_trades: dict[str, int]
    direction_net_pnl_usd: dict[str, float]
    forced_end_exits: int
    trade_records: tuple[dict[str, object], ...]
    execution_authority: str = "none"


def base_trial_grid() -> tuple[SwingHaSignalConfig, ...]:
    """Return the frozen base translation and EMA/pivot search grid."""
    return tuple(
        SwingHaSignalConfig(
            fast_ema=fast,
            slow_ema=slow,
            pivot_length=pivot,
            entry_mode=entry,
            exit_mode=exit_mode,
        )
        for (fast, slow), pivot, entry, exit_mode in product(
            _EMA_PAIRS, _PIVOT_LENGTHS, _ENTRY_MODES, _EXIT_MODES
        )
    )


def order_block_trial_grid(
    base: SwingHaSignalConfig,
) -> tuple[SwingHaSignalConfig, ...]:
    """Return one control plus frozen agreement and structural-stop variants."""
    control = replace(base, order_block_role="none")
    variants = tuple(
        replace(
            base,
            order_block_role=role,
            order_block_periods=periods,
            order_block_minimum_move_pct=move,
        )
        for role, periods, move in product(
            ("agreement", "structural_stop"), _OB_PERIODS, _OB_MOVES
        )
    )
    return (control, *variants)


def evaluate_swing_ha_cell(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    symbol: str,
    signal_config: SwingHaSignalConfig,
    venue_max_leverage: float,
    screen_config: SwingHaScreenConfig | None = None,
) -> SwingHaScreenCell:
    """Evaluate one complete cell and retain all trade evidence."""
    config = screen_config or SwingHaScreenConfig()
    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        config.portfolio_config(symbol=symbol, venue_max_leverage=venue_max_leverage),
    )
    trades = tuple(asdict(trade) for trade in report.trades)
    return SwingHaScreenCell(
        symbol=symbol,
        signal_config=asdict(signal_config),
        completed_trades=report.completed_trades,
        wins=report.wins,
        losses=report.losses,
        net_pnl_usd=report.net_pnl_usd,
        return_pct=report.return_pct,
        profit_factor=report.profit_factor,
        maximum_drawdown_pct=abs(report.maximum_drawdown_pct),
        liquidations=report.liquidations,
        total_fees_usd=report.total_fees_usd,
        funding_cashflow_usd=report.funding_cashflow_usd,
        direction_trades=_direction_counts(trades),
        direction_net_pnl_usd=_direction_net(trades),
        forced_end_exits=report.forced_end_exits,
        trade_records=trades,
    )


def delayed_signals(signals: pd.DataFrame, *, bars: int) -> pd.DataFrame:
    """Delay entry instructions while retaining original causal exit decisions."""
    if isinstance(bars, bool) or not isinstance(bars, int) or bars < 1:
        raise ValueError("entry delay must be a positive integer")
    output = signals.copy()
    for column in ("long_entry", "short_entry", "stop_price"):
        output[column] = output[column].shift(bars)
    output[["long_entry", "short_entry"]] = (
        output[["long_entry", "short_entry"]].fillna(False).astype(bool)
    )
    return output


def stress_screen_config() -> SwingHaScreenConfig:
    """Return a 20 bps round-trip taker-friction sensitivity."""
    return SwingHaScreenConfig(slippage_bps_per_side=5.5)


def signal_config_id(config: SwingHaSignalConfig) -> str:
    """Return a stable human-readable trial identity."""
    return (
        f"ema{config.fast_ema}x{config.slow_ema}_p{config.pivot_length}_"
        f"{config.entry_mode}_{config.exit_mode}_ob-{config.order_block_role}_"
        f"n{config.order_block_periods}_m{config.order_block_minimum_move_pct:g}"
    )


def _direction_counts(trades: tuple[dict[str, object], ...]) -> dict[str, int]:
    return {
        side: sum(trade["direction"] == side for trade in trades)
        for side in ("long", "short")
    }


def _direction_net(trades: tuple[dict[str, object], ...]) -> dict[str, float]:
    return {
        side: sum(
            float(trade["net_pnl_usd"])
            for trade in trades
            if trade["direction"] == side
        )
        for side in ("long", "short")
    }
