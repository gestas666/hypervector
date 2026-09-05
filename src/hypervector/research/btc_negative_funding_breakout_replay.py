"""Frozen economic replay for the BTC negative-funding breakout test."""

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
from hypervector.research.btc_negative_funding_hourly_breakout import (
    build_btc_negative_funding_breakout_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


@dataclass(frozen=True)
class BtcNegativeFundingBreakoutReplay:
    """Candidate and control economics under one authority-none contract."""

    candidate_report: SharedPortfolioReport
    control_report: SharedPortfolioReport
    candidate_signal_count: int
    control_signal_count: int
    candidate_signal_times_utc: tuple[str, ...]
    control_signal_times_utc: tuple[str, ...]
    slippage_bps_per_taker_side: float
    entry_delay_minutes: int
    execution_authority: str = "none"


def evaluate_btc_negative_funding_breakout(
    minute_bars: pd.DataFrame,
    hourly_funding: pd.Series,
    slippage_bps_per_taker_side: float,
    *,
    entry_delay_minutes: int = 0,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
) -> BtcNegativeFundingBreakoutReplay:
    """Replay the frozen candidate and unconditioned mechanism control."""
    label = "BTC negative-funding breakout"
    slippage = validated_btc_replay_slippage(slippage_bps_per_taker_side, label)
    delay = _validated_delay(entry_delay_minutes)
    start, end = validated_btc_entry_window(entry_start_utc, entry_end_utc, label)
    generated = build_btc_negative_funding_breakout_signals(
        minute_bars,
        hourly_funding,
    )
    candidate = _prepared_signals(
        generated.candidate_entries,
        minute_bars,
        delay,
        start,
        end,
    )
    control = _prepared_signals(
        generated.control_entries,
        minute_bars,
        delay,
        start,
        end,
    )
    market = validated_btc_replay_market(minute_bars, label)
    config = btc_fixed_60_60_portfolio_config(slippage)
    return BtcNegativeFundingBreakoutReplay(
        candidate_report=evaluate_shared_bar_portfolio(market, candidate, config),
        control_report=evaluate_shared_bar_portfolio(market, control, config),
        candidate_signal_count=int(candidate["long_entry"].sum()),
        control_signal_count=int(control["long_entry"].sum()),
        candidate_signal_times_utc=_signal_times(candidate),
        control_signal_times_utc=_signal_times(control),
        slippage_bps_per_taker_side=slippage,
        entry_delay_minutes=delay,
    )


def _validated_delay(value: int) -> int:
    if isinstance(value, bool) or value not in (0, 1):
        raise ValueError("BTC negative-funding entry delay must be zero or one minute")
    return value


def _prepared_signals(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
    delay: int,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    shifted = shift_btc_entry_signals(signals, bars, delay)
    return mask_btc_entry_window(shifted, start, end)


def _signal_times(signals: pd.DataFrame) -> tuple[str, ...]:
    return tuple(
        timestamp.isoformat()
        for timestamp in signals.index[signals["long_entry"].astype(bool)]
    )
