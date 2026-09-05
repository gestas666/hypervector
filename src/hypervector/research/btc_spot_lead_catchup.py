"""Causal signals for the report-only BTC spot-lead catch-up experiment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.research.btc_completed_bar_inputs import (
    completed_btc_bars,
    validated_btc_minute_bars,
)
from hypervector.strategies.indicators import ema


_FIFTEEN_MINUTES = pd.Timedelta(minutes=15)
_HOUR = pd.Timedelta(hours=1)
_MINUTE = pd.Timedelta(minutes=1)


@dataclass(frozen=True)
class BtcSpotLeadCatchupConfig:
    """Exact parameters from the authority-none preregistration."""

    fast_ema_hours: int = 21
    slow_ema_hours: int = 55
    prior_high_bars: int = 32
    placebo_lag_bars: int = 4
    report_only: bool = True
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject parameter or authority drift from the frozen contract."""
        identity = (
            self.fast_ema_hours,
            self.slow_ema_hours,
            self.prior_high_bars,
            self.placebo_lag_bars,
        )
        if identity != (21, 55, 32, 4):
            raise ValueError("BTC spot-lead catch-up parameters must stay frozen")
        if not self.report_only or self.execution_authority != "none":
            raise ValueError("BTC spot-lead catch-up research must remain report-only")


@dataclass(frozen=True)
class BtcSpotLeadCatchupSignals:
    """Primary, controls, and completed cross-venue diagnostics."""

    candidate_entries: pd.DataFrame
    native_control_entries: pd.DataFrame
    placebo_entries: pd.DataFrame
    completed_15m: pd.DataFrame
    completed_hourly: pd.DataFrame


def build_btc_spot_lead_catchup_signals(
    perpetual_minute_bars: pd.DataFrame,
    spot_minute_bars: pd.DataFrame,
    config: BtcSpotLeadCatchupConfig | None = None,
) -> BtcSpotLeadCatchupSignals:
    """Build the frozen cross-venue primary and its two controls."""
    frozen = config or BtcSpotLeadCatchupConfig()
    perpetual = validated_btc_minute_bars(perpetual_minute_bars, "BTC perpetual")
    spot = validated_btc_minute_bars(spot_minute_bars, "BTC Binance spot")
    if not perpetual.index.equals(spot.index):
        raise ValueError("BTC cross-venue inputs require identical UTC minute indexes")
    perpetual, spot = _joint_segments(perpetual, spot)
    perpetual_15m = completed_btc_bars(perpetual, "15min", 15)
    spot_15m = completed_btc_bars(spot, "15min", 15)
    if not perpetual_15m.index.equals(spot_15m.index):
        raise ValueError("BTC cross-venue completed fifteen-minute bars differ")
    hourly = completed_btc_bars(perpetual, "1h", 60)
    diagnostics = _diagnostics(perpetual_15m, spot_15m, hourly, frozen)
    return BtcSpotLeadCatchupSignals(
        candidate_entries=_project_entries(
            perpetual.index,
            diagnostics,
            "candidate_entry",
            "btc_spot_lead_catchup_long_v1",
        ),
        native_control_entries=_project_entries(
            perpetual.index,
            diagnostics,
            "native_control_entry",
            "btc_hl_native_15m_breakout_long_control_v1",
        ),
        placebo_entries=_project_entries(
            perpetual.index,
            diagnostics,
            "placebo_entry",
            "btc_spot_lead_60m_lag_placebo_long_v1",
        ),
        completed_15m=diagnostics,
        completed_hourly=hourly,
    )


def _joint_segments(
    perpetual: pd.DataFrame,
    spot: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    reset = perpetual["_gap_marker"] | spot["_gap_marker"]
    segment = reset.cumsum().astype(int)
    perpetual = perpetual.copy()
    spot = spot.copy()
    perpetual["_gap_marker"] = reset
    spot["_gap_marker"] = reset
    perpetual["segment_id"] = segment
    spot["segment_id"] = segment
    return perpetual, spot


def _diagnostics(
    perpetual: pd.DataFrame,
    spot: pd.DataFrame,
    hourly: pd.DataFrame,
    config: BtcSpotLeadCatchupConfig,
) -> pd.DataFrame:
    output = perpetual.add_prefix("perpetual_")
    output["spot_close"] = spot["close"]
    output["spot_high"] = spot["high"]
    output["segment_id"] = perpetual["segment_id"]
    output["spot_prior_32_high"] = _prior_high(spot, config.prior_high_bars)
    output["perpetual_prior_32_high"] = _prior_high(perpetual, config.prior_high_bars)
    output["hourly_trend_up"] = _hourly_trend(
        output.index + _FIFTEEN_MINUTES,
        output["segment_id"],
        hourly,
        config,
    )
    output["spot_breakout"] = output["spot_close"].gt(output["spot_prior_32_high"])
    output["perpetual_lag"] = output["perpetual_close"].le(
        output["perpetual_prior_32_high"]
    )
    output["perpetual_participation"] = _positive_change(output)
    output["spot_breakout_lag_4"] = _segmented_shift(
        output, "spot_breakout", config.placebo_lag_bars
    )
    common = (
        output["hourly_trend_up"]
        & output["perpetual_lag"]
        & output["perpetual_participation"]
    )
    output["candidate_raw"] = common & output["spot_breakout"]
    output["placebo_raw"] = common & output["spot_breakout_lag_4"]
    output["native_control_raw"] = output["hourly_trend_up"] & output[
        "perpetual_close"
    ].gt(output["perpetual_prior_32_high"])
    for name in ("candidate", "placebo", "native_control"):
        output[f"{name}_entry"] = _segmented_onsets(output, f"{name}_raw")
    return output


def _hourly_trend(
    boundaries: pd.DatetimeIndex,
    segments: pd.Series,
    hourly: pd.DataFrame,
    config: BtcSpotLeadCatchupConfig,
) -> np.ndarray:
    hourly = hourly.copy()
    hourly["ema21"] = hourly.groupby("segment_id", sort=False)["close"].transform(
        lambda values: ema(values, config.fast_ema_hours)
    )
    hourly["ema55"] = hourly.groupby("segment_id", sort=False)["close"].transform(
        lambda values: ema(values, config.slow_ema_hours)
    )
    ready = (
        hourly.groupby("segment_id", sort=False).cumcount().ge(config.slow_ema_hours)
    )
    trend = (
        ready
        & hourly["ema21"].gt(hourly["ema55"])
        & hourly["close"].gt(hourly["ema21"])
    )
    locations = (
        np.searchsorted((hourly.index + _HOUR).asi8, boundaries.asi8, side="right") - 1
    )
    output = np.zeros(len(boundaries), dtype=bool)
    valid = locations >= 0
    matched = (
        hourly["segment_id"].to_numpy()[locations[valid]] == segments.to_numpy()[valid]
    )
    output[valid] = trend.to_numpy()[locations[valid]] & matched
    return output


def _prior_high(bars: pd.DataFrame, lookback: int) -> pd.Series:
    output = pd.Series(np.nan, index=bars.index, dtype=float)
    for _, selected in bars.groupby("segment_id", sort=False):
        output.loc[selected.index] = selected["high"].shift(1).rolling(lookback).max()
    return output


def _positive_change(output: pd.DataFrame) -> pd.Series:
    change = output.groupby("segment_id", sort=False)["perpetual_close"].diff()
    return change.gt(0.0)


def _segmented_shift(output: pd.DataFrame, column: str, periods: int) -> pd.Series:
    return (
        output.groupby("segment_id", sort=False)[column]
        .shift(periods)
        .fillna(False)
        .astype(bool)
    )


def _segmented_onsets(output: pd.DataFrame, column: str) -> pd.Series:
    result = pd.Series(False, index=output.index, dtype=bool)
    for _, selected in output.groupby("segment_id", sort=False):
        raw = selected[column].fillna(False).astype(bool)
        result.loc[selected.index] = raw & ~raw.shift(1, fill_value=False)
    return result


def _project_entries(
    minute_index: pd.DatetimeIndex,
    diagnostics: pd.DataFrame,
    entry_column: str,
    signal_name: str,
) -> pd.DataFrame:
    output = pd.DataFrame(False, index=minute_index, columns=_signal_columns())
    endpoints = diagnostics.index + _FIFTEEN_MINUTES - _MINUTE
    valid = endpoints.isin(output.index)
    output.loc[endpoints[valid], "long_entry"] = diagnostics.loc[
        valid, entry_column
    ].to_numpy()
    output["long_signal_name"] = signal_name
    output["short_signal_name"] = "inactive_short"
    return output


def _signal_columns() -> tuple[str, ...]:
    return ("long_entry", "short_entry", "long_exit", "short_exit")
