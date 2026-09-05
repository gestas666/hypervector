"""Causal signals for the report-only V58 BTC sweep-relaxation replay."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import ema


_REQUIRED_COLUMNS = frozenset({"open", "high", "low", "close", "volume"})
_MINUTE = pd.Timedelta(minutes=1)
_HOUR = pd.Timedelta(hours=1)


@dataclass(frozen=True)
class BtcSweepPrimaryRelaxationConfig:
    """Parameters frozen in the V58 authority-none preregistration."""

    lookback_hours: int = 20
    sweep_clearance_bps: float = 2.0
    volume_multiple: float = 1.2
    ema_length_hours: int = 55
    report_only: bool = True
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject any post-registration parameter or authority drift."""
        if self.lookback_hours != 20:
            raise ValueError("frozen lookback must equal twenty hours")
        if not math.isclose(self.sweep_clearance_bps, 2.0):
            raise ValueError("frozen sweep clearance must equal two bps")
        if not math.isclose(self.volume_multiple, 1.2):
            raise ValueError("frozen volume multiple must equal 1.20x")
        if self.ema_length_hours != 55:
            raise ValueError("frozen EMA length must equal fifty-five hours")
        if not self.report_only or self.execution_authority != "none":
            raise ValueError("BTC sweep-relaxation research must remain report-only")


@dataclass(frozen=True)
class BtcSweepPrimaryRelaxationSignals:
    """Aligned control, candidate, and hourly predicate evidence."""

    control: pd.DataFrame
    candidate: pd.DataFrame
    hourly: pd.DataFrame


def build_btc_sweep_primary_relaxation_signals(
    minute_bars: pd.DataFrame,
    config: BtcSweepPrimaryRelaxationConfig | None = None,
) -> BtcSweepPrimaryRelaxationSignals:
    """Build exact-control and one-predicate-relaxed causal entry pulses."""
    frozen = config or BtcSweepPrimaryRelaxationConfig()
    market = _validated_minute_bars(minute_bars)
    hourly = _completed_hourly_bars(market)
    diagnostics = _hourly_diagnostics(hourly, frozen)
    return BtcSweepPrimaryRelaxationSignals(
        control=_project_entries(
            market.index,
            diagnostics,
            "control_entry",
            "liquidity_sweep_long_1h_stop60_target60_v2",
        ),
        candidate=_project_entries(
            market.index,
            diagnostics,
            "candidate_entry",
            "btc_sweep_primary_relaxation_long_v1",
        ),
        hourly=diagnostics,
    )


def _validated_minute_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"BTC sweep-relaxation bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("BTC sweep-relaxation bars require an aware DatetimeIndex")
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError("BTC sweep-relaxation bars must be unique and increasing")
    cadence = bars.index.to_series().diff().dropna()
    if len(bars) < 2 or not cadence.eq(_MINUTE).all():
        raise ValueError(
            "BTC sweep-relaxation requires uninterrupted one-minute cadence"
        )
    selected = bars.loc[:, sorted(_REQUIRED_COLUMNS)].astype(float).copy()
    _validate_market_values(selected)
    return selected


def _validate_market_values(bars: pd.DataFrame) -> None:
    ohlc = bars.loc[:, ["open", "high", "low", "close"]]
    if not np.isfinite(ohlc.to_numpy(dtype=float)).all() or (ohlc <= 0.0).any().any():
        raise ValueError("BTC sweep-relaxation OHLC must be finite and positive")
    volume = bars["volume"].to_numpy(dtype=float)
    if not np.isfinite(volume).all() or (volume < 0.0).any():
        raise ValueError("BTC sweep-relaxation volume must be finite and non-negative")
    if (ohlc["high"] < ohlc.max(axis=1)).any():
        raise ValueError("BTC sweep-relaxation high is internally inconsistent")
    if (ohlc["low"] > ohlc.min(axis=1)).any():
        raise ValueError("BTC sweep-relaxation low is internally inconsistent")


def _completed_hourly_bars(bars: pd.DataFrame) -> pd.DataFrame:
    grouped = bars.resample("1h", label="left", closed="left")
    hourly = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    result = hourly.loc[grouped.size().eq(60)].dropna()
    minimum = BtcSweepPrimaryRelaxationConfig().ema_length_hours + 1
    if len(result) < minimum:
        raise ValueError("BTC sweep-relaxation requires fifty-five prior hourly bars")
    return result


def _hourly_diagnostics(
    bars: pd.DataFrame,
    config: BtcSweepPrimaryRelaxationConfig,
) -> pd.DataFrame:
    prior_low = bars["low"].shift(1).rolling(config.lookback_hours).min()
    mean_volume = bars["volume"].shift(1).rolling(config.lookback_hours).mean()
    trend = ema(bars["close"], config.ema_length_hours)
    ready = pd.Series(np.arange(len(bars)) >= config.ema_length_hours, index=bars.index)
    sweep = bars["low"] < prior_low * (1.0 - config.sweep_clearance_bps / 10_000.0)
    reclaim = bars["close"] > prior_low
    volume_ok = bars["volume"] >= mean_volume * config.volume_multiple
    trend_ok = bars["close"] >= trend
    candidate_raw = ready & reclaim & volume_ok & trend_ok
    control_raw = candidate_raw & sweep
    output = pd.DataFrame(index=bars.index)
    output["prior_20h_low"] = prior_low
    output["mean_20h_volume"] = mean_volume
    output["ema55"] = trend
    output["sweep_ok"] = sweep
    output["reclaim"] = reclaim
    output["volume_ok"] = volume_ok
    output["trend_ok"] = trend_ok
    output["control_raw"] = control_raw
    output["candidate_raw"] = candidate_raw
    output["control_entry"] = _onsets(control_raw)
    output["candidate_entry"] = _onsets(candidate_raw)
    return output


def _onsets(values: pd.Series) -> pd.Series:
    clean = values.fillna(False).astype(bool)
    return clean & ~clean.shift(1, fill_value=False)


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
        valid, entry_column
    ].to_numpy()
    output["long_signal_name"] = signal_name
    output["short_signal_name"] = "inactive_short"
    return output


def _signal_columns() -> tuple[str, ...]:
    return ("long_entry", "short_entry", "long_exit", "short_exit")
