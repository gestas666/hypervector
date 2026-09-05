"""Causal signals for the report-only BTC trend-pullback experiment."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.btc_completed_bar_inputs import (
    completed_btc_bars,
    validated_btc_minute_bars,
)
from hypervector.strategies.indicators import ema


@dataclass(frozen=True)
class BtcTrendPullbackConfig:
    """Exact parameters from the authority-none preregistration."""

    fast_ema_hours: int = 21
    slow_ema_hours: int = 55
    pullback_expiry_bars: int = 8
    reacceleration_lookback_bars: int = 4
    report_only: bool = True
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject parameter or authority drift from the frozen contract."""
        parameters = (
            self.fast_ema_hours,
            self.slow_ema_hours,
            self.pullback_expiry_bars,
            self.reacceleration_lookback_bars,
        )
        if parameters != (21, 55, 8, 4):
            raise ValueError("BTC trend-pullback parameters must remain frozen")
        if not self.report_only or self.execution_authority != "none":
            raise ValueError("BTC trend-pullback research must remain report-only")


@dataclass(frozen=True)
class BtcTrendPullbackSignals:
    """Minute-aligned entry pulses and completed-bar diagnostics."""

    entries: pd.DataFrame
    diagnostics_15m: pd.DataFrame
    completed_hourly: pd.DataFrame


def build_btc_trend_pullback_signals(
    minute_bars: pd.DataFrame,
    config: BtcTrendPullbackConfig | None = None,
) -> BtcTrendPullbackSignals:
    """Build causal one-shot BTC pullback-reacceleration long entries."""
    frozen = config or BtcTrendPullbackConfig()
    market = validated_btc_minute_bars(minute_bars, "BTC trend-pullback")
    fifteen = completed_btc_bars(market, "15min", 15)
    hourly = completed_btc_bars(market, "1h", 60)
    if len(hourly) <= frozen.slow_ema_hours:
        raise ValueError("BTC trend-pullback requires fifty-five prior hourly bars")
    context = _hourly_context(hourly, frozen)
    diagnostics = _fifteen_minute_diagnostics(fifteen, context, frozen)
    return BtcTrendPullbackSignals(
        entries=_project_entries(market.index, diagnostics),
        diagnostics_15m=diagnostics,
        completed_hourly=context,
    )


def _hourly_context(
    hourly: pd.DataFrame, config: BtcTrendPullbackConfig
) -> pd.DataFrame:
    output = hourly.copy()
    grouped = output.groupby("segment_id", sort=False)["close"]
    output["ema21"] = grouped.transform(
        lambda values: ema(values, config.fast_ema_hours)
    )
    output["ema55"] = grouped.transform(
        lambda values: ema(values, config.slow_ema_hours)
    )
    ready = output.groupby("segment_id", sort=False).cumcount().to_numpy()
    output["trend_up"] = (
        (ready >= config.slow_ema_hours)
        & (output["ema21"] > output["ema55"])
        & (output["close"] > output["ema21"])
    )
    return output


def _fifteen_minute_diagnostics(
    fifteen: pd.DataFrame,
    hourly: pd.DataFrame,
    config: BtcTrendPullbackConfig,
) -> pd.DataFrame:
    output = fifteen.copy()
    mapped = _available_hourly_context(output, hourly)
    for column in ("ema21", "ema55", "trend_up"):
        output[column] = mapped[column].to_numpy()
    output["prior_local_high"] = (
        output["high"].shift(1).rolling(config.reacceleration_lookback_bars).max()
    )
    output["pullback_armed"] = False
    output["long_entry"] = False
    _apply_pullback_state(output, config)
    return output


def _available_hourly_context(
    fifteen: pd.DataFrame, hourly: pd.DataFrame
) -> pd.DataFrame:
    columns = ["ema21", "ema55", "trend_up"]
    mapped = pd.DataFrame(index=fifteen.index, columns=columns)
    for segment_id in fifteen["segment_id"].unique():
        selected = fifteen["segment_id"].eq(segment_id)
        decisions = fifteen.index[selected] + pd.Timedelta(minutes=15)
        available = hourly.loc[hourly["segment_id"].eq(segment_id), columns].copy()
        available.index = available.index + pd.Timedelta(hours=1)
        joined = (
            available.reindex(available.index.union(decisions)).sort_index().ffill()
        )
        values = joined.reindex(decisions)
        values.index = fifteen.index[selected]
        mapped.loc[selected, columns] = values
    return mapped


def _apply_pullback_state(
    diagnostics: pd.DataFrame, config: BtcTrendPullbackConfig
) -> None:
    armed_at: int | None = None
    prior_segment: int | None = None
    for position in range(len(diagnostics)):
        row = diagnostics.iloc[position]
        segment = int(row["segment_id"])
        if prior_segment is not None and segment != prior_segment:
            armed_at = None
        prior_segment = segment
        trend_up = bool(row["trend_up"]) if pd.notna(row["trend_up"]) else False
        context_ready = pd.notna(row["ema21"]) and pd.notna(row["ema55"])
        if not context_ready or not trend_up or row["close"] < row["ema55"]:
            armed_at = None
            continue
        if armed_at is not None and position - armed_at > config.pullback_expiry_bars:
            armed_at = None
        if armed_at is not None and _is_reacceleration(row):
            diagnostics.iloc[position, diagnostics.columns.get_loc("long_entry")] = True
            armed_at = None
            continue
        if armed_at is None and row["low"] <= row["ema21"]:
            armed_at = position
            diagnostics.iloc[
                position, diagnostics.columns.get_loc("pullback_armed")
            ] = True


def _is_reacceleration(row: pd.Series) -> bool:
    prior_high = row["prior_local_high"]
    return (
        pd.notna(prior_high)
        and row["close"] > prior_high
        and row["close"] > row["ema21"]
    )


def _project_entries(
    minute_index: pd.DatetimeIndex, diagnostics: pd.DataFrame
) -> pd.DataFrame:
    output = pd.DataFrame(False, index=minute_index, columns=_signal_columns())
    endpoints = diagnostics.index + pd.Timedelta(minutes=14)
    valid = endpoints.isin(output.index)
    output.loc[endpoints[valid], "long_entry"] = diagnostics.loc[
        valid, "long_entry"
    ].to_numpy()
    output["long_signal_name"] = "btc_trend_pullback_reacceleration_long_v1"
    output["short_signal_name"] = "inactive_short"
    return output


def _signal_columns() -> tuple[str, ...]:
    return ("long_entry", "short_entry", "long_exit", "short_exit")
