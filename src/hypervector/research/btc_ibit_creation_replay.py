"""Frozen V58-shaped economic replay for IBIT creation-persistence longs."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.btc_fixed_60_60_replay import (
    btc_fixed_60_60_portfolio_config,
    mask_btc_entry_window,
    shift_btc_entry_signals,
    validated_btc_entry_window,
    validated_btc_replay_market,
    validated_btc_replay_slippage,
)
from hypervector.research.btc_ibit_creation_long import (
    build_btc_ibit_creation_signals,
)
from hypervector.research.btc_sweep_primary_relaxation import (
    build_btc_sweep_primary_relaxation_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)


@dataclass(frozen=True)
class BtcIbitCreationReplay:
    """Four active-arm reports under one frozen report-only contract."""

    candidate_report: SharedPortfolioReport
    single_creation_control_report: SharedPortfolioReport
    redemption_placebo_report: SharedPortfolioReport
    v58_sweep_control_report: SharedPortfolioReport
    candidate_signal_count: int
    single_creation_signal_count: int
    redemption_placebo_signal_count: int
    v58_sweep_signal_count: int
    candidate_signal_times_utc: tuple[str, ...]
    single_creation_signal_times_utc: tuple[str, ...]
    redemption_placebo_signal_times_utc: tuple[str, ...]
    v58_sweep_signal_times_utc: tuple[str, ...]
    candidate_delay_gap_cancellations: int
    single_creation_delay_gap_cancellations: int
    redemption_placebo_delay_gap_cancellations: int
    slippage_bps_per_taker_side: float
    publication_delay_minutes: int
    execution_authority: str = "none"


def evaluate_btc_ibit_creation_long(
    minute_bars: pd.DataFrame,
    ibit_history: pd.DataFrame,
    slippage_bps_per_taker_side: float,
    *,
    publication_delay_minutes: int = 0,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
) -> BtcIbitCreationReplay:
    """Replay the frozen issuer candidate, controls, and V58 sweep."""
    label = "BTC IBIT creation long"
    delay = _validated_delay(publication_delay_minutes)
    slippage = validated_btc_replay_slippage(slippage_bps_per_taker_side, label)
    start, end = validated_btc_entry_window(entry_start_utc, entry_end_utc, label)
    market = validated_btc_replay_market(minute_bars, label)
    generated = build_btc_ibit_creation_signals(ibit_history, market.index)
    sweep = build_btc_sweep_primary_relaxation_signals(market).control
    candidate, candidate_gaps = _prepared_ibit(
        generated.candidate_entries, market, delay, start, end
    )
    single, single_gaps = _prepared_ibit(
        generated.single_creation_control_entries, market, delay, start, end
    )
    redemption, redemption_gaps = _prepared_ibit(
        generated.redemption_placebo_entries, market, delay, start, end
    )
    sweep = mask_btc_entry_window(sweep, start, end)
    config = btc_fixed_60_60_portfolio_config(slippage)
    return _result(
        market,
        config,
        candidate,
        single,
        redemption,
        sweep,
        (candidate_gaps, single_gaps, redemption_gaps),
        slippage,
        delay,
    )


def _validated_delay(value: int) -> int:
    if isinstance(value, bool) or value not in (0, 1_440):
        raise ValueError("BTC IBIT publication delay must be zero or 1440 minutes")
    return value


def _prepared_ibit(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
    delay: int,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> tuple[pd.DataFrame, int]:
    without_gap = shift_btc_entry_signals(
        signals,
        bars.drop(columns="gap_before_bars", errors="ignore"),
        delay,
    )
    shifted = shift_btc_entry_signals(signals, bars, delay)
    cancellations = _entry_count(without_gap) - _entry_count(shifted)
    return mask_btc_entry_window(shifted, start, end), cancellations


def _result(
    market: pd.DataFrame,
    config: SharedPortfolioConfig,
    candidate: pd.DataFrame,
    single: pd.DataFrame,
    redemption: pd.DataFrame,
    sweep: pd.DataFrame,
    gap_cancellations: tuple[int, int, int],
    slippage: float,
    delay: int,
) -> BtcIbitCreationReplay:
    return BtcIbitCreationReplay(
        candidate_report=evaluate_shared_bar_portfolio(market, candidate, config),
        single_creation_control_report=evaluate_shared_bar_portfolio(
            market, single, config
        ),
        redemption_placebo_report=evaluate_shared_bar_portfolio(
            market, redemption, config
        ),
        v58_sweep_control_report=evaluate_shared_bar_portfolio(market, sweep, config),
        candidate_signal_count=_entry_count(candidate),
        single_creation_signal_count=_entry_count(single),
        redemption_placebo_signal_count=_entry_count(redemption),
        v58_sweep_signal_count=_entry_count(sweep),
        candidate_signal_times_utc=_signal_times(candidate),
        single_creation_signal_times_utc=_signal_times(single),
        redemption_placebo_signal_times_utc=_signal_times(redemption),
        v58_sweep_signal_times_utc=_signal_times(sweep),
        candidate_delay_gap_cancellations=gap_cancellations[0],
        single_creation_delay_gap_cancellations=gap_cancellations[1],
        redemption_placebo_delay_gap_cancellations=gap_cancellations[2],
        slippage_bps_per_taker_side=slippage,
        publication_delay_minutes=delay,
    )


def _entry_count(signals: pd.DataFrame) -> int:
    return int(signals[["long_entry", "short_entry"]].to_numpy().sum())


def _signal_times(signals: pd.DataFrame) -> tuple[str, ...]:
    selected = signals["long_entry"].astype(bool)
    return tuple(timestamp.isoformat() for timestamp in signals.index[selected])
