"""Exact-quote development replay for HIP-3 oil shock reversion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from hypervector.research.hip3_archive_inputs import (
    signal_source_bars,
    validate_archive_bars,
    validate_archive_cadence,
    validate_archive_windows,
)
from hypervector.research.hip3_development_partitions import (
    evaluate_hip3_development_partitions,
)
from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
    build_hip3_oil_shock_reversion_signals,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


_INITIAL_EQUITY_USD = 500.0
_BAR_SECONDS = 300
OilSignalBuilder = Callable[[pd.DataFrame, Hip3OilShockReversionConfig], pd.DataFrame]


@dataclass(frozen=True)
class Hip3OilDevelopmentResult:
    """One frozen oil mechanism evaluated without out-of-sample economics."""

    symbol: str
    execution: MuArchiveExecution
    proposed_provider_id: str
    proposed_profile_id: str
    windows: MuChronologicalWindows
    signal: Hip3OilShockReversionConfig
    development: MuPartitionResult
    folds: tuple[MuPartitionResult, ...]
    out_of_sample_economics: str = "WITHHELD_NOT_EVALUATED"
    execution_authority: str = "none"
    automatic_promotion: bool = False


def hip3_oil_reversion_portfolio_config(
    execution: MuArchiveExecution,
    signal: Hip3OilShockReversionConfig,
    *,
    stress: bool,
) -> SharedPortfolioConfig:
    """Return the frozen 5x, target/stop, and one-hour fallback contract."""
    leverage = min(5.0, execution.venue_max_leverage)
    latency = (
        execution.stress_latency_bps_per_side
        if stress
        else execution.nominal_latency_bps_per_side
    )
    slippage = latency + (execution.stress_visible_tail_bps_per_side if stress else 0.0)
    fee = execution.effective_taker_fee_rate
    return SharedPortfolioConfig(
        symbol=execution.symbol,
        initial_equity=_INITIAL_EQUITY_USD,
        margin_fraction=execution.notional_usd / (_INITIAL_EQUITY_USD * leverage),
        leverage=leverage,
        venue_max_leverage=execution.venue_max_leverage,
        target_margin_pct=signal.target_bps * leverage / 100.0,
        stop_margin_pct=signal.stop_bps * leverage / 100.0,
        maximum_stop_distance_bps=signal.stop_bps,
        entry_fee_rate=fee,
        target_fee_rate=fee,
        market_exit_fee_rate=fee,
        liquidation_fee_rate=fee,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
        max_hold_bars=signal.maximum_hold_bars,
        max_hold_seconds=signal.maximum_hold_bars * _BAR_SECONDS,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=True,
        open_bid_column="entry_bid",
        open_ask_column="entry_ask",
        close_bid_column="decision_bid",
        close_ask_column="decision_ask",
        risk_high_column=execution.risk_high_column,
        risk_low_column=execution.risk_low_column,
        entry_risk_high_column=execution.entry_risk_high_column,
        entry_risk_low_column=execution.entry_risk_low_column,
    )


def evaluate_hip3_oil_shock_reversion_development(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    windows: MuChronologicalWindows,
    signal: Hip3OilShockReversionConfig = Hip3OilShockReversionConfig(),
) -> Hip3OilDevelopmentResult:
    """Replay one frozen five-minute mechanism on development evidence only."""
    return evaluate_hip3_oil_shock_development(
        bars,
        execution,
        windows=windows,
        signal=signal,
        signal_builder=build_hip3_oil_shock_reversion_signals,
        family="reversion",
    )


def evaluate_hip3_oil_shock_development(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    windows: MuChronologicalWindows,
    signal: Hip3OilShockReversionConfig,
    signal_builder: OilSignalBuilder,
    family: str,
) -> Hip3OilDevelopmentResult:
    """Replay one named frozen oil-shock family on development evidence only."""
    if family not in {"reversion", "continuation"}:
        raise ValueError("oil shock family must be reversion or continuation")
    validate_archive_bars(bars)
    validate_archive_cadence(bars, "5m", execution.maximum_hold_bars)
    validate_archive_windows(bars, windows, "5m")
    causal = bars.loc[bars.index < windows.development_end_utc].copy()
    signals = signal_builder(signal_source_bars(causal), signal)
    development, folds = evaluate_hip3_development_partitions(
        causal,
        signals,
        windows,
        lambda stress: hip3_oil_reversion_portfolio_config(
            execution, signal, stress=stress
        ),
    )
    slug = execution.symbol.split(":", maxsplit=1)[1].lower()
    return Hip3OilDevelopmentResult(
        execution.symbol,
        execution,
        f"hip3_{slug}_oil_shock_{family}_bidirectional_5m_research_v1",
        f"{slug}_oil_shock_{family}_5m_development_v1",
        windows,
        signal,
        development,
        folds,
    )
