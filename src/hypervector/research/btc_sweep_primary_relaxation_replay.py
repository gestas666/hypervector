"""V58-shaped economic replay for BTC sweep-primary relaxation."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.research.btc_sweep_primary_relaxation import (
    build_btc_sweep_primary_relaxation_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)


_FUNDING_COLUMN = "funding_rate"


@dataclass(frozen=True)
class BtcSweepPrimaryRelaxationReplay:
    """Control and candidate economics under one identical contract."""

    control: SharedPortfolioReport
    candidate: SharedPortfolioReport
    control_signal_count: int
    candidate_signal_count: int
    slippage_bps_per_taker_side: float
    control_signal_times_utc: tuple[str, ...] = ()
    candidate_signal_times_utc: tuple[str, ...] = ()


def evaluate_btc_sweep_primary_relaxation(
    minute_bars: pd.DataFrame,
    slippage_bps_per_taker_side: float,
    *,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
) -> BtcSweepPrimaryRelaxationReplay:
    """Replay control and candidate without granting execution authority."""
    slippage = _validated_slippage(slippage_bps_per_taker_side)
    signals = build_btc_sweep_primary_relaxation_signals(minute_bars)
    start, end = _validated_entry_window(entry_start_utc, entry_end_utc)
    control = _mask_entry_window(signals.control, start, end)
    candidate = _mask_entry_window(signals.candidate, start, end)
    market = _replay_market(minute_bars)
    config = _portfolio_config(slippage)
    return BtcSweepPrimaryRelaxationReplay(
        control=evaluate_shared_bar_portfolio(market, control, config),
        candidate=evaluate_shared_bar_portfolio(market, candidate, config),
        control_signal_count=int(control["long_entry"].sum()),
        candidate_signal_count=int(candidate["long_entry"].sum()),
        slippage_bps_per_taker_side=slippage,
        control_signal_times_utc=_signal_times(control),
        candidate_signal_times_utc=_signal_times(candidate),
    )


def _signal_times(signals: pd.DataFrame) -> tuple[str, ...]:
    return tuple(
        timestamp.isoformat()
        for timestamp in signals.index[signals["long_entry"].astype(bool)]
    )


def _validated_entry_window(
    start_utc: pd.Timestamp | None,
    end_utc: pd.Timestamp | None,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    start = _optional_utc_timestamp(start_utc, "entry start")
    end = _optional_utc_timestamp(end_utc, "entry end")
    if start is not None and end is not None and start >= end:
        raise ValueError("BTC sweep-relaxation entry start must precede entry end")
    return start, end


def _optional_utc_timestamp(
    value: pd.Timestamp | None,
    label: str,
) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f"BTC sweep-relaxation {label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _mask_entry_window(
    signals: pd.DataFrame,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    output = signals.copy()
    selected = pd.Series(True, index=output.index)
    if start is not None:
        selected &= output.index >= start
    if end is not None:
        selected &= output.index < end
    output.loc[~selected, ["long_entry", "short_entry"]] = False
    return output


def _validated_slippage(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(
            "BTC sweep-relaxation slippage must be finite and non-negative"
        )
    return numeric


def _replay_market(bars: pd.DataFrame) -> pd.DataFrame:
    if _FUNDING_COLUMN not in bars:
        raise ValueError("BTC sweep-relaxation replay requires exact funding_rate")
    market = bars.copy()
    funding = pd.to_numeric(market[_FUNDING_COLUMN], errors="raise").astype(float)
    if not np.isfinite(funding.to_numpy()).all():
        raise ValueError("BTC sweep-relaxation funding must be finite")
    market[_FUNDING_COLUMN] = funding
    market["gap_before_bars"] = 0
    return market


def _portfolio_config(slippage: float) -> SharedPortfolioConfig:
    return SharedPortfolioConfig(
        symbol="BTC",
        initial_equity=5_000.0,
        margin_fraction=0.10,
        leverage=10.0,
        venue_max_leverage=40.0,
        maximum_notional_usd=5_000.0,
        target_margin_pct=6.0,
        stop_margin_pct=6.0,
        maximum_stop_distance_bps=60.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
        liquidation_slippage_bps=slippage,
        max_hold_bars=1_440,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=False,
    )
