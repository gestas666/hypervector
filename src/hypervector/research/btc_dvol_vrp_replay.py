"""Frozen V58-shaped economic replay for the BTC DVOL-VRP long trial."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.btc_dvol_vrp_continuation import (
    build_btc_dvol_vrp_signals,
)
from hypervector.research.btc_fixed_60_60_replay import (
    mask_btc_entry_window,
    shift_btc_entry_signals,
    validated_btc_entry_window,
    validated_btc_replay_market,
)
from hypervector.research.btc_sweep_primary_relaxation import (
    build_btc_sweep_primary_relaxation_signals,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)


_SCENARIOS: dict[str, tuple[float, int]] = {
    "nominal": (2.0, 0),
    "stress": (5.0, 5),
    "delayed": (10.0, 60),
}
_SIGNAL_COLUMNS = ("long_entry", "short_entry", "long_exit", "short_exit")


@dataclass(frozen=True)
class BtcDvolVrpReplay:
    """Five active-arm reports under one frozen authority-none contract."""

    primary_report: SharedPortfolioReport
    price_only_report: SharedPortfolioReport
    high_vrp_only_report: SharedPortfolioReport
    low_vrp_placebo_report: SharedPortfolioReport
    v58_sweep_report: SharedPortfolioReport
    primary_signal_count: int
    price_only_signal_count: int
    high_vrp_only_signal_count: int
    low_vrp_placebo_signal_count: int
    v58_sweep_signal_count: int
    primary_signal_times_utc: tuple[str, ...]
    price_only_signal_times_utc: tuple[str, ...]
    high_vrp_only_signal_times_utc: tuple[str, ...]
    low_vrp_placebo_signal_times_utc: tuple[str, ...]
    v58_sweep_signal_times_utc: tuple[str, ...]
    primary_delay_gap_cancellations: int
    price_only_delay_gap_cancellations: int
    high_vrp_only_delay_gap_cancellations: int
    low_vrp_placebo_delay_gap_cancellations: int
    v58_sweep_delay_gap_cancellations: int
    scenario: str
    slippage_bps_per_taker_side: float
    extra_delay_minutes: int
    execution_authority: str = "none"


def evaluate_btc_dvol_vrp_long(
    minute_bars: pd.DataFrame,
    features: pd.DataFrame,
    scenario: str,
    *,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
) -> BtcDvolVrpReplay:
    """Replay the frozen DVOL-VRP candidate, controls, and V58 sweep."""
    slippage, delay = _scenario(scenario)
    start, end = validated_btc_entry_window(
        entry_start_utc,
        entry_end_utc,
        "BTC DVOL-VRP long",
    )
    market = validated_btc_replay_market(minute_bars, "BTC DVOL-VRP long")
    generated = build_btc_dvol_vrp_signals(features)
    projected = tuple(_project(frame, market.index) for frame in generated.frames())
    prepared = tuple(_prepared(frame, market, delay, start, end) for frame in projected)
    sweep_raw = build_btc_sweep_primary_relaxation_signals(market).control
    sweep = _prepared(sweep_raw, market, delay, start, end)
    return _result(market, prepared, sweep, scenario, slippage, delay)


def _scenario(name: str) -> tuple[float, int]:
    contract = _SCENARIOS.get(name)
    if contract is None:
        raise ValueError(f"BTC DVOL-VRP replay unknown scenario: {name}")
    return contract


def _project(signals: pd.DataFrame, minute_index: pd.DatetimeIndex) -> pd.DataFrame:
    output = pd.DataFrame(False, index=minute_index, columns=_SIGNAL_COLUMNS)
    event_times = pd.DatetimeIndex(signals["event_time"])
    in_market = event_times.isin(minute_index)
    selected_times = event_times[in_market]
    for column in _SIGNAL_COLUMNS:
        output.loc[selected_times, column] = signals.loc[in_market, column].to_numpy()
    output["signal_name"] = str(signals["signal_name"].iloc[0])
    return output


def _prepared(
    signals: pd.DataFrame,
    bars: pd.DataFrame,
    delay: int,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> tuple[pd.DataFrame, int]:
    bars_without_gaps = bars.drop(columns="gap_before_bars", errors="ignore")
    uncensored = shift_btc_entry_signals(signals, bars_without_gaps, delay)
    shifted = shift_btc_entry_signals(signals, bars, delay)
    cancellations = _entry_count(uncensored) - _entry_count(shifted)
    return mask_btc_entry_window(shifted, start, end), cancellations


def _portfolio_config(slippage: float) -> SharedPortfolioConfig:
    return SharedPortfolioConfig(
        symbol="BTC",
        initial_equity=5_000.0,
        margin_fraction=0.10,
        leverage=10.0,
        venue_max_leverage=40.0,
        maximum_notional_usd=5_000.0,
        target_margin_pct=25.0,
        stop_margin_pct=10.0,
        maximum_stop_distance_bps=100.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
        liquidation_slippage_bps=slippage,
        max_hold_bars=4_320,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=True,
        close_on_opposite_signal=False,
    )


def _result(
    market: pd.DataFrame,
    prepared: tuple[tuple[pd.DataFrame, int], ...],
    sweep: tuple[pd.DataFrame, int],
    scenario: str,
    slippage: float,
    delay: int,
) -> BtcDvolVrpReplay:
    primary, price, high, low = prepared
    frames = (primary[0], price[0], high[0], low[0], sweep[0])
    reports = tuple(
        evaluate_shared_bar_portfolio(market, frame, _portfolio_config(slippage))
        for frame in frames
    )
    counts = tuple(_entry_count(frame) for frame in frames)
    times = tuple(_signal_times(frame) for frame in frames)
    gaps = (primary[1], price[1], high[1], low[1], sweep[1])
    return BtcDvolVrpReplay(
        *reports,
        *counts,
        *times,
        *gaps,
        scenario,
        slippage,
        delay,
    )


def _entry_count(signals: pd.DataFrame) -> int:
    return int(signals[["long_entry", "short_entry"]].to_numpy().sum())


def _signal_times(signals: pd.DataFrame) -> tuple[str, ...]:
    selected = signals["long_entry"].astype(bool) | signals["short_entry"].astype(bool)
    return tuple(timestamp.isoformat() for timestamp in signals.index[selected])
