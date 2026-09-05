"""Frozen placebo and unchanged sweep controls for BTC option flow."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

import pandas as pd

from hypervector.research.btc_sweep_primary_relaxation import (
    build_btc_sweep_primary_relaxation_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)


_MINUTE = pd.Timedelta(minutes=1)


class SweepSignalSetProtocol(Protocol):
    """Minimal result contract required from the frozen sweep builder."""

    control: pd.DataFrame


class SweepSignalBuilderProtocol(Protocol):
    """Callable contract for causal frozen sweep signal construction."""

    def __call__(self, bars: pd.DataFrame) -> SweepSignalSetProtocol:
        """Return a control signal frame aligned to signal-only bars."""
        ...


@dataclass(frozen=True)
class BtcOptionFlowSweepControlReplay:
    """One unchanged sweep-control replay and routing counts."""

    report: SharedPortfolioReport
    raw_signal_count: int
    scheduled_signal_count: int
    displaced_signal_count: int
    partition_excluded_signal_count: int
    slippage_bps_per_market_side: float
    extra_delay_minutes: int


def direction_inverted_placebo_flow(flow: pd.DataFrame) -> pd.DataFrame:
    """Swap bullish and bearish extreme onsets without changing availability."""
    required = {"available_at", "long_onset", "opposing_onset"}
    missing = sorted(required.difference(flow.columns))
    if missing:
        raise ValueError(f"option-flow placebo input missing columns: {missing}")
    output = flow.loc[:, ["available_at", "long_onset", "opposing_onset"]].copy()
    long_onset = output["long_onset"].astype(bool).copy()
    output["long_onset"] = output["opposing_onset"].astype(bool)
    output["opposing_onset"] = long_onset
    return output


def evaluate_btc_option_flow_sweep_control(
    execution_bars: pd.DataFrame,
    signal_bars: pd.DataFrame,
    *,
    slippage_bps_per_market_side: float,
    extra_delay_minutes: int = 0,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
    signal_builder: SweepSignalBuilderProtocol = (
        build_btc_sweep_primary_relaxation_signals
    ),
) -> BtcOptionFlowSweepControlReplay:
    """Replay the unchanged 60/60-bps sweep route on gap-aware execution bars."""
    slippage = _validated_slippage(slippage_bps_per_market_side)
    delay = _validated_delay(extra_delay_minutes)
    start, end = _entry_window(entry_start_utc, entry_end_utc)
    source = signal_builder(signal_bars).control
    signals, counts = _project_control_signals(
        execution_bars.index, source, delay, start, end
    )
    report = evaluate_shared_bar_portfolio(
        execution_bars, signals, _portfolio_config(slippage)
    )
    return BtcOptionFlowSweepControlReplay(
        report,
        counts[0],
        counts[1],
        counts[2],
        counts[3],
        slippage,
        delay,
    )


def _project_control_signals(
    index: pd.DatetimeIndex,
    source: pd.DataFrame,
    delay_minutes: int,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> tuple[pd.DataFrame, tuple[int, int, int, int]]:
    if not isinstance(source.index, pd.DatetimeIndex) or source.index.tz is None:
        raise ValueError("sweep-control signals require an aware DatetimeIndex")
    if "long_entry" not in source:
        raise ValueError("sweep-control source lacks long_entry")
    raw_times = source.index[source["long_entry"].astype(bool)]
    signals = _empty_signals(index)
    scheduled = displaced = excluded = 0
    delay = pd.Timedelta(minutes=delay_minutes)
    for timestamp in raw_times:
        signal_at = pd.Timestamp(timestamp).tz_convert("UTC") + delay
        available = signal_at + _MINUTE
        if not _inside(available, start, end):
            excluded += 1
        elif signal_at not in index:
            displaced += 1
        else:
            signals.loc[signal_at, "long_entry"] = True
            scheduled += 1
    return signals, (len(raw_times), scheduled, displaced, excluded)


def _empty_signals(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "long_entry": False,
            "short_entry": False,
            "long_exit": False,
            "short_exit": False,
            "long_signal_name": "liquidity_sweep_long_1h_stop60_target60_v2",
        },
        index=index,
    )


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
        max_hold_seconds=86_400,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=False,
    )


def _entry_window(
    start: pd.Timestamp | None, end: pd.Timestamp | None
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    start_at = _optional_utc(start, "entry start")
    end_at = _optional_utc(end, "entry end")
    if start_at is not None and end_at is not None and start_at >= end_at:
        raise ValueError("sweep-control entry bounds must be increasing")
    return start_at, end_at


def _optional_utc(value: pd.Timestamp | None, label: str) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"sweep-control {label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _inside(
    timestamp: pd.Timestamp,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> bool:
    return (start is None or timestamp >= start) and (end is None or timestamp < end)


def _validated_slippage(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError("sweep-control slippage must be finite and nonnegative")
    return numeric


def _validated_delay(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("sweep-control delay must be a nonnegative integer")
    return value
