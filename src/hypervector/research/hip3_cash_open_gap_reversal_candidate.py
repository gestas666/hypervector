"""Development-only exact-quote replay for HIP-3 cash-open gap reversal."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.hip3_archive_inputs import (
    signal_source_bars,
    validate_archive_bar_timing,
    validate_archive_bars,
    validate_archive_windows,
)
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
    build_hip3_cash_open_gap_reversal_signals,
)
from hypervector.research.hip3_development_partitions import (
    evaluate_hip3_development_partitions,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


_INITIAL_EQUITY_USD = 5000.0
_LEVERAGE = 10.0
_BAR_SECONDS = 900
_FROZEN_NOTIONAL_USD = {
    "xyz:SP500": 5000.0,
    "xyz:SPCX": 5000.0,
    "xyz:MU": 2000.0,
}


@dataclass(frozen=True)
class Hip3CashOpenGapDevelopmentResult:
    """One frozen symbol evaluated without validation or holdout economics."""

    symbol: str
    execution: MuArchiveExecution
    proposed_provider_id: str
    proposed_profile_id: str
    windows: MuChronologicalWindows
    signal: Hip3CashOpenGapReversalConfig
    development: MuPartitionResult
    folds: tuple[MuPartitionResult, ...]
    out_of_sample_economics: str = "WITHHELD_NOT_EVALUATED"
    execution_authority: str = "none"
    automatic_promotion: bool = False


def hip3_cash_open_gap_reversal_portfolio_config(
    execution: MuArchiveExecution,
    signal: Hip3CashOpenGapReversalConfig,
    *,
    stress: bool,
) -> SharedPortfolioConfig:
    """Return the frozen $5K, 10x, stop, and cash-session exit contract."""
    _validate_execution(execution, signal)
    latency = (
        execution.stress_latency_bps_per_side
        if stress
        else execution.nominal_latency_bps_per_side
    )
    tail = execution.stress_visible_tail_bps_per_side if stress else 0.0
    fee = execution.effective_taker_fee_rate
    return SharedPortfolioConfig(
        symbol=execution.symbol,
        initial_equity=_INITIAL_EQUITY_USD,
        margin_fraction=execution.notional_usd / (_INITIAL_EQUITY_USD * _LEVERAGE),
        leverage=_LEVERAGE,
        venue_max_leverage=execution.venue_max_leverage,
        stop_margin_pct=signal.stop_bps * _LEVERAGE / 100.0,
        maximum_stop_distance_bps=signal.stop_bps,
        entry_fee_rate=fee,
        target_fee_rate=fee,
        market_exit_fee_rate=fee,
        liquidation_fee_rate=fee,
        entry_slippage_bps=latency + tail,
        market_exit_slippage_bps=latency + tail,
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


def evaluate_hip3_cash_open_gap_reversal_development(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    windows: MuChronologicalWindows,
    signal: Hip3CashOpenGapReversalConfig = Hip3CashOpenGapReversalConfig(),
) -> Hip3CashOpenGapDevelopmentResult:
    """Replay the single preregistered 15-minute mechanism on development."""
    validate_archive_bars(bars)
    validate_archive_bar_timing(bars, "15m")
    validate_archive_windows(bars, windows, "15m")
    _validate_execution(execution, signal)
    causal = bars.loc[bars.index < windows.development_end_utc].copy()
    signals = build_hip3_cash_open_gap_reversal_signals(
        signal_source_bars(causal), signal
    )
    development, folds = evaluate_hip3_development_partitions(
        causal,
        signals,
        windows,
        lambda stress: hip3_cash_open_gap_reversal_portfolio_config(
            execution, signal, stress=stress
        ),
    )
    slug = execution.symbol.split(":", maxsplit=1)[1].lower()
    return Hip3CashOpenGapDevelopmentResult(
        execution.symbol,
        execution,
        f"hip3_{slug}_cash_open_gap_reversal_bidirectional_15m_research_v1",
        f"{slug}_cash_open_gap_reversal_15m_development_v1",
        windows,
        signal,
        development,
        folds,
    )


def _validate_execution(
    execution: MuArchiveExecution,
    signal: Hip3CashOpenGapReversalConfig,
) -> None:
    """Require exact symbol, leverage, notional, stop, and holding identity."""
    expected_notional = _FROZEN_NOTIONAL_USD.get(execution.symbol)
    if expected_notional is None:
        raise ValueError("cash-open replay symbol has no frozen transfer contract")
    if execution.venue_max_leverage < _LEVERAGE:
        raise ValueError("cash-open venue leverage is below the frozen 10x")
    if execution.notional_usd != expected_notional:
        raise ValueError("cash-open replay requires the symbol's frozen notional")
    if execution.fixed_stop_bps != signal.stop_bps:
        raise ValueError("cash-open execution stop differs from signal stop")
    if execution.maximum_hold_bars != signal.maximum_hold_bars:
        raise ValueError("cash-open execution and signal horizons differ")
