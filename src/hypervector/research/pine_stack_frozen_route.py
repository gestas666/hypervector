"""Single-identity later-window replay for the four-Pine strategy stack."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import pandas as pd

from hypervector.research.pine_stack_portfolio_adapter import (
    PineStackExitVariant,
    declared_pine_stack_exit_variants,
    pine_stack_portfolio_signals,
)
from hypervector.research.pine_stack_screen import PineStackScreenConfig
from hypervector.research.pine_stack_signals import declared_pine_stack_candidates
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)


@dataclass(frozen=True)
class FrozenPineRoute:
    """Exact Pine candidate identity frozen before later-window evaluation."""

    symbol: str
    bar_minutes: int
    candidate: str
    exit_variant: PineStackExitVariant

    def __post_init__(self) -> None:
        """Reject undeclared or ambiguous route identities."""
        if not self.symbol or self.symbol != self.symbol.strip().upper():
            raise ValueError("frozen Pine route symbol must be uppercase")
        if self.bar_minutes not in {15, 30}:
            raise ValueError("frozen Pine route timeframe must be 15m or 30m")
        if self.candidate not in declared_pine_stack_candidates():
            raise ValueError("frozen Pine route candidate is not declared")
        if self.exit_variant not in declared_pine_stack_exit_variants():
            raise ValueError("frozen Pine route exit variant is not declared")


@dataclass(frozen=True)
class FrozenPinePartitionResult:
    """Nominal and stressed evidence for one frozen route and partition."""

    route: FrozenPineRoute
    signal_count: int
    nominal: SharedPortfolioReport
    stress: SharedPortfolioReport
    execution_authority: str = "none"

    def to_dict(self) -> dict[str, object]:
        """Return complete report-only evidence with robustness summaries."""
        return {
            "route": asdict(self.route),
            "signal_count": self.signal_count,
            "execution_authority": self.execution_authority,
            "nominal": _scenario_payload(self.nominal),
            "stress": _scenario_payload(self.stress),
        }


def frozen_sol30_route() -> FrozenPineRoute:
    """Return the sole SOL identity selected by the Stage-A development screen."""
    return FrozenPineRoute("SOL", 30, "cs_trend", "cs_flip")


def evaluate_frozen_pine_partition(
    *,
    bars: pd.DataFrame,
    features: pd.DataFrame,
    entries: pd.DataFrame,
    route: FrozenPineRoute,
    venue_max_leverage: float,
    nominal_config: PineStackScreenConfig,
    stress_config: PineStackScreenConfig,
) -> FrozenPinePartitionResult:
    """Replay one predeclared route without evaluating neighboring identities."""
    _validate_market_identity(bars, features, entries, route)
    _validate_stress(nominal_config, stress_config)
    signals = pine_stack_portfolio_signals(
        features,
        entries,
        candidate=route.candidate,
        exit_variant=route.exit_variant,
    )
    nominal = _evaluate(bars, signals, route, venue_max_leverage, nominal_config)
    stress = _evaluate(bars, signals, route, venue_max_leverage, stress_config)
    signal_count = int(entries["candidate"].eq(route.candidate).sum())
    return FrozenPinePartitionResult(route, signal_count, nominal, stress)


def _evaluate(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    route: FrozenPineRoute,
    venue_max_leverage: float,
    config: PineStackScreenConfig,
) -> SharedPortfolioReport:
    portfolio = config.portfolio_config(
        symbol=route.symbol,
        bar_minutes=route.bar_minutes,
        venue_max_leverage=venue_max_leverage,
    )
    return evaluate_shared_bar_portfolio(
        bars.set_index("bar_open_at").copy(), signals, portfolio
    )


def _validate_market_identity(
    bars: pd.DataFrame,
    features: pd.DataFrame,
    entries: pd.DataFrame,
    route: FrozenPineRoute,
) -> None:
    required_bars = {"bar_open_at", "open", "high", "low", "close", "funding_rate"}
    missing = sorted(required_bars.difference(bars.columns))
    if missing:
        raise ValueError(f"frozen Pine bars missing columns: {missing}")
    bar_times = pd.DatetimeIndex(bars["bar_open_at"])
    feature_times = pd.DatetimeIndex(features["bar_open_at"])
    if not bar_times.equals(feature_times):
        raise ValueError("frozen Pine bars and features must share exact times")
    if "symbol" not in entries or not entries["symbol"].eq(route.symbol).all():
        raise ValueError("frozen Pine entries do not match route symbol")
    if "candidate" not in entries:
        raise ValueError("frozen Pine entries lack candidate identity")


def _validate_stress(
    nominal: PineStackScreenConfig,
    stress: PineStackScreenConfig,
) -> None:
    ordered_fields = (
        "fee_rate_per_side",
        "maker_target_fee_rate",
        "slippage_bps_per_side",
    )
    if any(getattr(stress, name) < getattr(nominal, name) for name in ordered_fields):
        raise ValueError("frozen Pine stress friction cannot be cheaper than nominal")
    invariant_fields = (
        "initial_equity",
        "margin_fraction",
        "leverage",
        "stop_margin_pct",
        "maximum_hold_hours",
        "reentry_cooldown_bars",
    )
    if any(
        getattr(stress, name) != getattr(nominal, name) for name in invariant_fields
    ):
        raise ValueError("frozen Pine stress may change friction only")


def _scenario_payload(report: SharedPortfolioReport) -> dict[str, object]:
    return {
        "all": _report_summary(report),
        "by_side": {
            side: _trade_summary(
                [trade for trade in report.trades if trade.direction == side]
            )
            for side in ("long", "short")
        },
        "monthly_net_pnl_usd": report.monthly_net_pnl_usd,
        "trades": [asdict(trade) for trade in report.trades],
        "limitations": list(report.limitations),
    }


def _report_summary(report: SharedPortfolioReport) -> dict[str, object]:
    summary = _trade_summary(report.trades)
    return {
        **summary,
        "initial_equity_usd": report.initial_equity,
        "final_equity_usd": report.final_equity,
        "return_pct": report.return_pct,
        "maximum_drawdown_pct": abs(report.maximum_drawdown_pct),
        "liquidations": report.liquidations,
        "total_fees_usd": report.total_fees_usd,
        "funding_cashflow_usd": report.funding_cashflow_usd,
        "forced_end_exits": report.forced_end_exits,
    }


def _trade_summary(trades: Sequence[SharedPortfolioTrade]) -> dict[str, object]:
    values = [trade.net_pnl_usd for trade in trades]
    profits = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_profit = sum(profits)
    gross_loss = abs(sum(losses))
    largest = max(profits, default=0.0)
    return {
        "completed_trades": len(values),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": sum(values),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "largest_winner_usd": largest if profits else None,
        "net_excluding_largest_winner_usd": sum(values) - largest,
    }
