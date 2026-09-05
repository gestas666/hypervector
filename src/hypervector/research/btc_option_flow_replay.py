"""Live-shaped economic replay for the frozen BTC option-flow candidate."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)


_SIGNAL_TO_ENTRY_DELAY = pd.Timedelta(minutes=1)
_MAXIMUM_HOLD_SECONDS = 86_400


@dataclass(frozen=True)
class BtcOptionFlowReplay:
    """One frozen scenario replay and its signal-routing diagnostics."""

    report: SharedPortfolioReport
    long_signal_count: int
    opposing_signal_count: int
    displaced_signal_count: int
    slippage_bps_per_market_side: float
    extra_delay_minutes: int


def evaluate_btc_option_flow_replay(
    minute_bars: pd.DataFrame,
    flow_signals: pd.DataFrame,
    *,
    slippage_bps_per_market_side: float,
    extra_delay_minutes: int = 0,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
) -> BtcOptionFlowReplay:
    """Replay one report-only BTC option-flow scenario with exact exits."""
    slippage = _validated_slippage(slippage_bps_per_market_side)
    delay = _validated_delay(extra_delay_minutes)
    bars = _validated_bars(minute_bars)
    flow = _validated_flow(flow_signals)
    start, end = _entry_window(entry_start_utc, entry_end_utc)
    signals, counts = _minute_signals(bars.index, flow, delay, start, end)
    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _portfolio_config(slippage),
    )
    return BtcOptionFlowReplay(
        report,
        counts[0],
        counts[1],
        counts[2],
        slippage,
        delay,
    )


def _validated_slippage(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError("BTC option-flow slippage must be finite and nonnegative")
    return numeric


def _validated_delay(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("BTC option-flow delay must be a nonnegative integer")
    return value


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("BTC option-flow minute bars require an aware datetime index")
    if "funding_rate" not in bars:
        raise ValueError("BTC option-flow minute bars require exact funding_rate")
    output = bars.copy()
    output.index = output.index.tz_convert("UTC")
    if "gap_before_bars" not in output:
        output["gap_before_bars"] = 0
    gaps = pd.to_numeric(output["gap_before_bars"], errors="raise")
    if gaps.isna().any() or (gaps < 0).any() or not gaps.mod(1).eq(0).all():
        raise ValueError("BTC option-flow gap counts must be nonnegative integers")
    output["gap_before_bars"] = gaps.astype(int)
    return output


def _validated_flow(flow: pd.DataFrame) -> pd.DataFrame:
    required = {"available_at", "long_onset", "opposing_onset"}
    missing = sorted(required.difference(flow.columns))
    if missing:
        raise ValueError(f"BTC option-flow signals missing columns: {missing}")
    output = flow.loc[:, sorted(required)].copy()
    output["available_at"] = pd.to_datetime(output["available_at"], utc=True)
    timestamps = pd.DatetimeIndex(output["available_at"])
    if (
        timestamps.hasnans
        or timestamps.has_duplicates
        or not timestamps.is_monotonic_increasing
    ):
        raise ValueError("BTC option-flow availability must be ordered and unique")
    for column in ("long_onset", "opposing_onset"):
        if not output[column].isin((True, False)).all():
            raise ValueError(f"BTC option-flow {column} must be boolean")
        output[column] = output[column].astype(bool)
    if (output["long_onset"] & output["opposing_onset"]).any():
        raise ValueError("BTC option-flow onsets cannot conflict")
    return output


def _entry_window(
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    start_at = _optional_utc(start, "entry start")
    end_at = _optional_utc(end, "entry end")
    if start_at is not None and end_at is not None and start_at >= end_at:
        raise ValueError("BTC option-flow entry bounds must be increasing")
    return start_at, end_at


def _optional_utc(value: pd.Timestamp | None, label: str) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"BTC option-flow {label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _minute_signals(
    index: pd.DatetimeIndex,
    flow: pd.DataFrame,
    delay_minutes: int,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> tuple[pd.DataFrame, tuple[int, int, int]]:
    signals = _empty_signals(index)
    long_count = opposing_count = displaced = 0
    delay = pd.Timedelta(minutes=delay_minutes)
    for row in flow.itertuples(index=False):
        available = pd.Timestamp(row.available_at) + delay
        signal_at = available - _SIGNAL_TO_ENTRY_DELAY
        long_relevant = bool(row.long_onset) and _inside(available, start, end)
        opposing_relevant = bool(row.opposing_onset) and _inside_index(signal_at, index)
        if signal_at not in index:
            displaced += int(long_relevant) + int(opposing_relevant)
            continue
        if long_relevant:
            signals.loc[signal_at, "long_entry"] = True
            long_count += 1
        if bool(row.opposing_onset):
            signals.loc[signal_at, "long_exit"] = True
            opposing_count += 1
    return signals, (long_count, opposing_count, displaced)


def _inside_index(timestamp: pd.Timestamp, index: pd.DatetimeIndex) -> bool:
    return len(index) > 0 and index[0] <= timestamp <= index[-1]


def _empty_signals(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "long_entry": False,
            "short_entry": False,
            "long_exit": False,
            "short_exit": False,
            "long_signal_name": "btc_deribit_otm_directional_flow_long_v1",
        },
        index=index,
    )


def _inside(
    timestamp: pd.Timestamp,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> bool:
    return (start is None or timestamp >= start) and (end is None or timestamp < end)


def _portfolio_config(slippage: float) -> SharedPortfolioConfig:
    return SharedPortfolioConfig(
        symbol="BTC",
        initial_equity=5_000.0,
        margin_fraction=0.10,
        leverage=10.0,
        venue_max_leverage=40.0,
        maximum_notional_usd=5_000.0,
        target_margin_pct=20.0,
        stop_margin_pct=10.0,
        maximum_stop_distance_bps=100.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
        liquidation_slippage_bps=slippage,
        max_hold_seconds=_MAXIMUM_HOLD_SECONDS,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=False,
    )
