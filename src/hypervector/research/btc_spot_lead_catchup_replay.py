"""Frozen economic replay for the BTC spot-lead catch-up experiment."""

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
from hypervector.research.btc_spot_lead_catchup import (
    build_btc_spot_lead_catchup_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


@dataclass(frozen=True)
class BtcSpotLeadCatchupReplay:
    """Primary and two control economics under one frozen contract."""

    candidate_report: SharedPortfolioReport
    native_control_report: SharedPortfolioReport
    placebo_report: SharedPortfolioReport
    candidate_signal_count: int
    native_control_signal_count: int
    placebo_signal_count: int
    candidate_signal_times_utc: tuple[str, ...]
    native_control_signal_times_utc: tuple[str, ...]
    placebo_signal_times_utc: tuple[str, ...]
    slippage_bps_per_taker_side: float
    entry_delay_minutes: int
    execution_authority: str = "none"


def evaluate_btc_spot_lead_catchup(
    perpetual_minute_bars: pd.DataFrame,
    spot_minute_bars: pd.DataFrame,
    slippage_bps_per_taker_side: float,
    *,
    entry_delay_minutes: int = 0,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
) -> BtcSpotLeadCatchupReplay:
    """Replay the frozen spot-lead primary and both active controls."""
    label = "BTC spot-lead catch-up"
    slippage = validated_btc_replay_slippage(slippage_bps_per_taker_side, label)
    delay = _validated_delay(entry_delay_minutes)
    start, end = validated_btc_entry_window(entry_start_utc, entry_end_utc, label)
    generated = build_btc_spot_lead_catchup_signals(
        perpetual_minute_bars,
        spot_minute_bars,
    )
    candidate = _prepared(
        generated.candidate_entries, perpetual_minute_bars, delay, start, end
    )
    native = _prepared(
        generated.native_control_entries, perpetual_minute_bars, delay, start, end
    )
    placebo = _prepared(
        generated.placebo_entries, perpetual_minute_bars, delay, start, end
    )
    market = validated_btc_replay_market(perpetual_minute_bars, label)
    config = btc_fixed_60_60_portfolio_config(slippage)
    return BtcSpotLeadCatchupReplay(
        candidate_report=evaluate_shared_bar_portfolio(market, candidate, config),
        native_control_report=evaluate_shared_bar_portfolio(market, native, config),
        placebo_report=evaluate_shared_bar_portfolio(market, placebo, config),
        candidate_signal_count=int(candidate["long_entry"].sum()),
        native_control_signal_count=int(native["long_entry"].sum()),
        placebo_signal_count=int(placebo["long_entry"].sum()),
        candidate_signal_times_utc=_signal_times(candidate),
        native_control_signal_times_utc=_signal_times(native),
        placebo_signal_times_utc=_signal_times(placebo),
        slippage_bps_per_taker_side=slippage,
        entry_delay_minutes=delay,
    )


def _validated_delay(value: int) -> int:
    if isinstance(value, bool) or value not in (0, 1):
        raise ValueError("BTC spot-lead entry delay must be zero or one minute")
    return value


def _prepared(
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
