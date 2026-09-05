"""Development-only exact-quote replay for the HIP-3 opening range."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pandas as pd

from hypervector.research.hip3_archive_inputs import (
    signal_source_bars,
    validate_archive_bars,
    validate_archive_windows,
)
from hypervector.research.hip3_development_partitions import (
    evaluate_hip3_development_partitions,
)
from hypervector.research.hip3_opening_range_breakout_signals import (
    Hip3OpeningRangeBreakoutConfig,
    build_hip3_opening_range_breakout_signals,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


_INITIAL_EQUITY_USD = 5000.0
_LEVERAGE = 10.0
_MAXIMUM_HOLD_SECONDS = 21_600
_SUPPORTED_SYMBOLS = frozenset({"xyz:SP500", "xyz:SPCX"})


@dataclass(frozen=True)
class Hip3OpeningRangeDevelopmentResult:
    """One frozen symbol evaluated without validation or holdout economics."""

    symbol: str
    execution: MuArchiveExecution
    proposed_provider_id: str
    proposed_profile_id: str
    windows: MuChronologicalWindows
    signal: Hip3OpeningRangeBreakoutConfig
    development: MuPartitionResult
    folds: tuple[MuPartitionResult, ...]
    out_of_sample_economics: str = "WITHHELD_NOT_EVALUATED"
    execution_authority: str = "none"
    automatic_promotion: bool = False


def hip3_opening_range_breakout_portfolio_config(
    execution: MuArchiveExecution,
    signal: Hip3OpeningRangeBreakoutConfig,
    *,
    stress: bool,
) -> SharedPortfolioConfig:
    """Return the frozen v53-sized exact-quote execution contract."""
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
        stop_margin_pct=signal.maximum_stop_bps * _LEVERAGE / 100.0,
        maximum_stop_distance_bps=signal.maximum_stop_bps,
        entry_fee_rate=fee,
        target_fee_rate=fee,
        market_exit_fee_rate=fee,
        liquidation_fee_rate=fee,
        entry_slippage_bps=latency + tail,
        market_exit_slippage_bps=latency + tail,
        max_hold_bars=signal.maximum_hold_bars,
        max_hold_seconds=_MAXIMUM_HOLD_SECONDS,
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


def evaluate_hip3_opening_range_breakout_development(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    windows: MuChronologicalWindows,
    signal: Hip3OpeningRangeBreakoutConfig,
) -> Hip3OpeningRangeDevelopmentResult:
    """Replay the single preregistered 15-minute mechanism on development."""
    validate_archive_bars(bars)
    validate_archive_windows(bars, windows, "15m")
    _validate_15m_cadence(bars, execution, signal)
    causal = bars.loc[bars.index < windows.development_end_utc].copy()
    signals = build_hip3_opening_range_breakout_signals(
        signal_source_bars(causal), signal
    )
    development, folds = evaluate_hip3_development_partitions(
        causal,
        signals,
        windows,
        lambda stress: hip3_opening_range_breakout_portfolio_config(
            execution, signal, stress=stress
        ),
    )
    slug = execution.symbol.split(":", maxsplit=1)[1].lower()
    return Hip3OpeningRangeDevelopmentResult(
        execution.symbol,
        execution,
        f"hip3_{slug}_us_cash_opening_range_breakout_bidirectional_15m_v1",
        f"{slug}_us_cash_opening_range_breakout_15m_development_v1",
        windows,
        signal,
        development,
        folds,
    )


def _validate_execution(
    execution: MuArchiveExecution, signal: Hip3OpeningRangeBreakoutConfig
) -> None:
    """Require the exact symbol, leverage, notional, stop, and horizon."""
    if execution.symbol not in _SUPPORTED_SYMBOLS:
        raise ValueError("opening-range replay requires exact SP500 or SPCX identity")
    if execution.venue_max_leverage < _LEVERAGE:
        raise ValueError("opening-range venue leverage is below the frozen 10x")
    if execution.notional_usd != 5000.0:
        raise ValueError("opening-range replay requires the frozen $5000 notional")
    if execution.fixed_stop_bps != signal.maximum_stop_bps:
        raise ValueError("opening-range execution stop differs from signal ceiling")
    if execution.maximum_hold_bars != signal.maximum_hold_bars:
        raise ValueError("opening-range execution and signal horizons differ")


def _validate_15m_cadence(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    signal: Hip3OpeningRangeBreakoutConfig,
) -> None:
    """Reconcile gaps, quote timing, and the frozen six-hour ceiling."""
    _validate_execution(execution, signal)
    elapsed = bars.index.to_series().diff().dt.total_seconds().iloc[1:]
    expected = (bars["gap_before_bars"].astype(int).iloc[1:] + 1) * 900
    if not elapsed.eq(expected).all():
        raise ValueError("opening-range bars violate declared 15-minute cadence")
    for column in (
        "first_boundary_delay_ms",
        "end_boundary_age_ms",
        "maximum_snapshot_interval_ms",
    ):
        values = pd.to_numeric(bars[column], errors="raise").astype(float)
        upper = (
            values.lt(900_000)
            if column == "first_boundary_delay_ms"
            else values.le(900_000)
        )
        if not values.map(isfinite).all() or values.lt(0.0).any() or not upper.all():
            raise ValueError(f"opening-range {column} is outside the 15m bar")
