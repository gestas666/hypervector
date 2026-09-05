"""Exact-quote development replay for HIP-3 Krown trend resumption."""

from __future__ import annotations

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
from hypervector.research.hip3_krown_trend_resumption_signals import (
    Hip3KrownTrendResumptionConfig,
    build_hip3_krown_trend_resumption_signals,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig


_INITIAL_EQUITY_USD = 500.0
_MAXIMUM_HOLD_SECONDS = 86_400


@dataclass(frozen=True)
class Hip3KrownDevelopmentResult:
    """One frozen Krown mechanism evaluated without out-of-sample economics."""

    symbol: str
    execution: MuArchiveExecution
    proposed_provider_id: str
    proposed_profile_id: str
    windows: MuChronologicalWindows
    signal: Hip3KrownTrendResumptionConfig
    development: MuPartitionResult
    folds: tuple[MuPartitionResult, ...]
    out_of_sample_economics: str = "WITHHELD_NOT_EVALUATED"
    execution_authority: str = "none"
    automatic_promotion: bool = False


def hip3_krown_trend_resumption_portfolio_config(
    execution: MuArchiveExecution,
    signal: Hip3KrownTrendResumptionConfig,
    *,
    stress: bool,
) -> SharedPortfolioConfig:
    """Return the frozen 5x, 80-bps stop, and 24-hour fallback contract."""
    leverage = min(5.0, execution.venue_max_leverage)
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
        margin_fraction=execution.notional_usd / (_INITIAL_EQUITY_USD * leverage),
        leverage=leverage,
        venue_max_leverage=execution.venue_max_leverage,
        stop_margin_pct=signal.protective_stop_bps * leverage / 100.0,
        maximum_stop_distance_bps=signal.protective_stop_bps,
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


def evaluate_hip3_krown_trend_resumption_development(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    *,
    windows: MuChronologicalWindows,
    signal: Hip3KrownTrendResumptionConfig = Hip3KrownTrendResumptionConfig(),
) -> Hip3KrownDevelopmentResult:
    """Replay the single predeclared 15-minute mechanism on development only."""
    validate_archive_bars(bars)
    validate_archive_cadence(bars, "15m", execution.maximum_hold_bars)
    validate_archive_windows(bars, windows, "15m")
    causal = bars.loc[bars.index < windows.development_end_utc].copy()
    signals = build_hip3_krown_trend_resumption_signals(
        signal_source_bars(causal), signal
    )
    development, folds = evaluate_hip3_development_partitions(
        causal,
        signals,
        windows,
        lambda stress: hip3_krown_trend_resumption_portfolio_config(
            execution, signal, stress=stress
        ),
    )
    slug = execution.symbol.split(":", maxsplit=1)[1].lower()
    return Hip3KrownDevelopmentResult(
        execution.symbol,
        execution,
        f"hip3_{slug}_krown_trend_resumption_bidirectional_15m_research_v1",
        f"{slug}_krown_trend_resumption_15m_development_v1",
        windows,
        signal,
        development,
        folds,
    )
