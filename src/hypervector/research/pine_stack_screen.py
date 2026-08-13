"""Complete-cell bar screen for the causal four-Pine strategy stack."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import pandas as pd

from hypervector.research.pine_stack_portfolio_adapter import (
    PineStackExitVariant,
    declared_pine_stack_exit_variants,
    pine_stack_portfolio_signals,
)
from hypervector.research.pine_stack_signals import declared_pine_stack_candidates
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)


@dataclass(frozen=True)
class PineStackScreenConfig:
    """Frozen capital, friction, risk, and duration assumptions for Stage A."""

    initial_equity: float = 15_000.0
    margin_fraction: float = 0.10
    leverage: float = 5.0
    stop_margin_pct: float = 10.0
    maximum_hold_hours: int = 8
    fee_rate_per_side: float = 0.00045
    maker_target_fee_rate: float = 0.00015
    slippage_bps_per_side: float = 2.0
    reentry_cooldown_bars: int = 1

    def __post_init__(self) -> None:
        """Reject invalid capital, cost, risk, and duration assumptions."""
        positive = (
            self.initial_equity,
            self.margin_fraction,
            self.leverage,
            self.stop_margin_pct,
            self.fee_rate_per_side,
            self.maker_target_fee_rate,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("Pine screen economic assumptions must be positive")
        if self.margin_fraction > 1.0:
            raise ValueError("Pine screen margin fraction cannot exceed one")
        if isinstance(self.maximum_hold_hours, bool) or self.maximum_hold_hours < 1:
            raise ValueError("Pine screen maximum hold hours must be positive")
        if (
            not math.isfinite(self.slippage_bps_per_side)
            or self.slippage_bps_per_side < 0
        ):
            raise ValueError("Pine screen slippage must be non-negative")
        if (
            isinstance(self.reentry_cooldown_bars, bool)
            or self.reentry_cooldown_bars < 0
        ):
            raise ValueError("Pine screen cooldown bars must be non-negative")

    def portfolio_config(
        self,
        *,
        symbol: str,
        bar_minutes: int,
        venue_max_leverage: float,
    ) -> SharedPortfolioConfig:
        """Return duration-matched isolated-margin portfolio assumptions."""
        total_minutes = self.maximum_hold_hours * 60
        if bar_minutes not in {15, 30} or total_minutes % bar_minutes:
            raise ValueError("Pine screen hold duration must divide native bars")
        return SharedPortfolioConfig(
            symbol=symbol,
            initial_equity=self.initial_equity,
            margin_fraction=self.margin_fraction,
            leverage=self.leverage,
            venue_max_leverage=venue_max_leverage,
            stop_margin_pct=self.stop_margin_pct,
            entry_fee_rate=self.fee_rate_per_side,
            target_fee_rate=self.maker_target_fee_rate,
            market_exit_fee_rate=self.fee_rate_per_side,
            liquidation_fee_rate=self.fee_rate_per_side,
            entry_slippage_bps=self.slippage_bps_per_side,
            market_exit_slippage_bps=self.slippage_bps_per_side,
            max_hold_bars=total_minutes // bar_minutes,
            reentry_cooldown_bars=self.reentry_cooldown_bars,
        )


@dataclass(frozen=True)
class PineStackScreenCell:
    """One independent asset/timeframe/entry/exit development result."""

    symbol: str
    bar_minutes: int
    candidate: str
    exit_variant: PineStackExitVariant
    signal_count: int
    completed_trades: int
    wins: int
    losses: int
    initial_equity: float
    final_equity: float
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    liquidations: int
    total_fees_usd: float
    funding_cashflow_usd: float
    ambiguous_trades: int
    forced_end_exits: int
    limitations: tuple[str, ...]
    trade_records: tuple[dict[str, object], ...]
    execution_authority: str = "none"


def evaluate_pine_stack_cells(
    *,
    bars: pd.DataFrame,
    features: pd.DataFrame,
    entries: pd.DataFrame,
    symbol: str,
    bar_minutes: int,
    venue_max_leverage: float,
    config: PineStackScreenConfig | None = None,
) -> tuple[PineStackScreenCell, ...]:
    """Evaluate every declared entry/exit cell and preserve empty trials."""
    cfg = config or PineStackScreenConfig()
    market = _indexed_market(bars, features)
    portfolio = cfg.portfolio_config(
        symbol=symbol,
        bar_minutes=bar_minutes,
        venue_max_leverage=venue_max_leverage,
    )
    cells: list[PineStackScreenCell] = []
    for candidate in declared_pine_stack_candidates():
        signal_count = int(entries["candidate"].eq(candidate).sum())
        for exit_variant in declared_pine_stack_exit_variants():
            signals = pine_stack_portfolio_signals(
                features,
                entries,
                candidate=candidate,
                exit_variant=exit_variant,
            )
            report = evaluate_shared_bar_portfolio(market, signals, portfolio)
            cells.append(
                _screen_cell(
                    report,
                    symbol,
                    bar_minutes,
                    candidate,
                    exit_variant,
                    signal_count,
                )
            )
    return tuple(cells)


def _indexed_market(bars: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    required = {"bar_open_at", "open", "high", "low", "close", "funding_rate"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"Pine screen bars missing columns: {missing}")
    bar_times = pd.DatetimeIndex(bars["bar_open_at"])
    feature_times = pd.DatetimeIndex(features["bar_open_at"])
    if not bar_times.equals(feature_times):
        raise ValueError("Pine screen bars and features must share native times")
    return bars.set_index("bar_open_at").copy()


def _screen_cell(
    report: SharedPortfolioReport,
    symbol: str,
    bar_minutes: int,
    candidate: str,
    exit_variant: PineStackExitVariant,
    signal_count: int,
) -> PineStackScreenCell:
    return PineStackScreenCell(
        symbol,
        bar_minutes,
        candidate,
        exit_variant,
        signal_count,
        report.completed_trades,
        report.wins,
        report.losses,
        report.initial_equity,
        report.final_equity,
        report.net_pnl_usd,
        report.profit_factor,
        abs(report.maximum_drawdown_pct),
        report.liquidations,
        report.total_fees_usd,
        report.funding_cashflow_usd,
        sum(trade.same_bar_ambiguous for trade in report.trades),
        report.forced_end_exits,
        report.limitations,
        tuple(asdict(trade) for trade in report.trades),
    )
