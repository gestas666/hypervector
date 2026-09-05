"""Causal signals for the report-only BTC negative-funding breakout test."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.research.btc_completed_bar_inputs import (
    completed_btc_bars,
    validated_btc_minute_bars,
)
from hypervector.strategies.indicators import ema


_HOUR = pd.Timedelta(hours=1)
_MINUTE = pd.Timedelta(minutes=1)


@dataclass(frozen=True)
class BtcNegativeFundingBreakoutConfig:
    """Exact parameters from the authority-none preregistration."""

    fast_ema_hours: int = 21
    slow_ema_hours: int = 55
    prior_high_hours: int = 20
    report_only: bool = True
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject parameter or authority drift from the frozen contract."""
        if (self.fast_ema_hours, self.slow_ema_hours, self.prior_high_hours) != (
            21,
            55,
            20,
        ):
            raise ValueError(
                "BTC negative-funding breakout parameters must stay frozen"
            )
        if not self.report_only or self.execution_authority != "none":
            raise ValueError(
                "BTC negative-funding breakout research must remain report-only"
            )


@dataclass(frozen=True)
class BtcNegativeFundingBreakoutSignals:
    """Candidate, mechanism-control, and completed-hour evidence."""

    candidate_entries: pd.DataFrame
    control_entries: pd.DataFrame
    completed_hourly: pd.DataFrame


def build_btc_negative_funding_breakout_signals(
    minute_bars: pd.DataFrame,
    hourly_funding: pd.Series,
    config: BtcNegativeFundingBreakoutConfig | None = None,
) -> BtcNegativeFundingBreakoutSignals:
    """Build the frozen candidate and unconditioned-control entry pulses."""
    frozen = config or BtcNegativeFundingBreakoutConfig()
    market = validated_btc_minute_bars(
        minute_bars,
        "BTC negative-funding breakout",
    )
    hourly = completed_btc_bars(market, "1h", 60)
    if len(hourly) <= frozen.slow_ema_hours:
        raise ValueError(
            "BTC negative-funding breakout requires fifty-five prior hourly bars"
        )
    funding = _validated_hourly_funding(hourly_funding)
    diagnostics = _hourly_diagnostics(hourly, funding, frozen)
    return BtcNegativeFundingBreakoutSignals(
        candidate_entries=_project_entries(
            market.index,
            diagnostics,
            "candidate_entry",
            "btc_negative_funding_hourly_breakout_long_v1",
        ),
        control_entries=_project_entries(
            market.index,
            diagnostics,
            "control_entry",
            "btc_unconditioned_hourly_breakout_long_control_v1",
        ),
        completed_hourly=diagnostics,
    )


def _validated_hourly_funding(values: pd.Series) -> pd.Series:
    if not isinstance(values, pd.Series):
        raise TypeError("BTC negative-funding feature requires a funding Series")
    if not isinstance(values.index, pd.DatetimeIndex) or values.index.tz is None:
        raise ValueError("BTC negative-funding timestamps must be timezone-aware")
    if not values.index.is_unique or not values.index.is_monotonic_increasing:
        raise ValueError("BTC negative-funding rows must be unique and increasing")
    numeric = pd.to_numeric(values, errors="raise").astype(float)
    if numeric.empty or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("BTC negative-funding rates must be finite and nonempty")
    cadence = numeric.index.to_series().diff().dropna()
    if not cadence.eq(_HOUR).all():
        raise ValueError("BTC negative-funding rows must have hourly cadence")
    return numeric.rename("funding_rate")


def _hourly_diagnostics(
    hourly: pd.DataFrame,
    funding: pd.Series,
    config: BtcNegativeFundingBreakoutConfig,
) -> pd.DataFrame:
    output = hourly.copy()
    output["ema21"] = _segmented_ema(output, config.fast_ema_hours)
    output["ema55"] = _segmented_ema(output, config.slow_ema_hours)
    output["prior_20h_high"] = _segmented_prior_high(
        output,
        config.prior_high_hours,
    )
    output["latest_prior_funding_rate"] = _strictly_prior_funding(
        output.index + _HOUR,
        funding,
    )
    ready = output.groupby("segment_id", sort=False).cumcount()
    output["trend_up"] = (
        ready.ge(config.slow_ema_hours)
        & output["ema21"].gt(output["ema55"])
        & output["close"].gt(output["ema21"])
    )
    output["breakout"] = output["close"].gt(output["prior_20h_high"])
    output["negative_funding"] = output["latest_prior_funding_rate"].lt(0.0)
    output["control_raw"] = output["trend_up"] & output["breakout"]
    output["candidate_raw"] = output["control_raw"] & output["negative_funding"]
    output["control_entry"] = _segmented_onsets(output, "control_raw")
    output["candidate_entry"] = _segmented_onsets(output, "candidate_raw")
    return output


def _segmented_ema(hourly: pd.DataFrame, period: int) -> pd.Series:
    return hourly.groupby("segment_id", sort=False)["close"].transform(
        lambda values: ema(values, period)
    )


def _segmented_prior_high(hourly: pd.DataFrame, lookback: int) -> pd.Series:
    output = pd.Series(np.nan, index=hourly.index, dtype=float)
    for _, selected in hourly.groupby("segment_id", sort=False):
        output.loc[selected.index] = selected["high"].shift(1).rolling(lookback).max()
    return output


def _strictly_prior_funding(
    boundaries: pd.DatetimeIndex,
    funding: pd.Series,
) -> np.ndarray:
    locations = (
        np.searchsorted(
            funding.index.asi8,
            boundaries.asi8,
            side="left",
        )
        - 1
    )
    if (locations < 0).any():
        raise ValueError("BTC breakout decision has no strictly prior funding row")
    return funding.to_numpy(dtype=float)[locations]


def _segmented_onsets(hourly: pd.DataFrame, column: str) -> pd.Series:
    output = pd.Series(False, index=hourly.index, dtype=bool)
    for _, selected in hourly.groupby("segment_id", sort=False):
        raw = selected[column].fillna(False).astype(bool)
        output.loc[selected.index] = raw & ~raw.shift(1, fill_value=False)
    return output


def _project_entries(
    minute_index: pd.DatetimeIndex,
    hourly: pd.DataFrame,
    entry_column: str,
    signal_name: str,
) -> pd.DataFrame:
    output = pd.DataFrame(False, index=minute_index, columns=_signal_columns())
    endpoints = hourly.index + _HOUR - _MINUTE
    valid = endpoints.isin(output.index)
    output.loc[endpoints[valid], "long_entry"] = hourly.loc[
        valid,
        entry_column,
    ].to_numpy()
    output["long_signal_name"] = signal_name
    output["short_signal_name"] = "inactive_short"
    return output


def _signal_columns() -> tuple[str, ...]:
    return ("long_entry", "short_entry", "long_exit", "short_exit")
