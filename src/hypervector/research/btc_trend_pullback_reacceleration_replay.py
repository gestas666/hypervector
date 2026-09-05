"""Frozen economic replay for BTC trend-pullback reacceleration."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.btc_fixed_60_60_replay import (
    btc_fixed_60_60_portfolio_config,
    mask_btc_entry_window,
    validated_btc_entry_window,
    validated_btc_replay_market,
    validated_btc_replay_slippage,
)
from hypervector.research.btc_trend_pullback_reacceleration import (
    build_btc_trend_pullback_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
)


@dataclass(frozen=True)
class BtcTrendPullbackReplay:
    """Candidate economics under one exact authority-none contract."""

    report: SharedPortfolioReport
    signal_count: int
    slippage_bps_per_taker_side: float
    signal_times_utc: tuple[str, ...]


def evaluate_btc_trend_pullback_reacceleration(
    minute_bars: pd.DataFrame,
    slippage_bps_per_taker_side: float,
    *,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
) -> BtcTrendPullbackReplay:
    """Replay the frozen candidate without granting execution authority."""
    label = "BTC trend-pullback"
    slippage = validated_btc_replay_slippage(slippage_bps_per_taker_side, label)
    generated = build_btc_trend_pullback_signals(minute_bars)
    start, end = validated_btc_entry_window(entry_start_utc, entry_end_utc, label)
    signals = mask_btc_entry_window(generated.entries, start, end)
    report = evaluate_shared_bar_portfolio(
        validated_btc_replay_market(minute_bars, label),
        signals,
        btc_fixed_60_60_portfolio_config(slippage),
    )
    return BtcTrendPullbackReplay(
        report=report,
        signal_count=int(signals["long_entry"].sum()),
        slippage_bps_per_taker_side=slippage,
        signal_times_utc=tuple(
            timestamp.isoformat()
            for timestamp in signals.index[signals["long_entry"].astype(bool)]
        ),
    )
