"""Causal five-minute shock-reversion signals for exact HIP-3 oil evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class Hip3OilShockReversionConfig:
    """Frozen return, threshold, and barrier parameters for oil reversion."""

    return_lookback_bars: int = 12
    threshold_lookback_bars: int = 2_016
    minimum_history_bars: int = 1_000
    shock_quantile: float = 0.95
    target_bps: float = 40.0
    stop_bps: float = 30.0
    maximum_hold_bars: int = 12

    def __post_init__(self) -> None:
        """Reject ambiguous or non-finite signal parameters."""
        integers = (
            self.return_lookback_bars,
            self.threshold_lookback_bars,
            self.minimum_history_bars,
            self.maximum_hold_bars,
        )
        if any(isinstance(value, bool) or value <= 0 for value in integers):
            raise ValueError("oil reversion bar counts must be positive integers")
        if self.minimum_history_bars > self.threshold_lookback_bars:
            raise ValueError("minimum history cannot exceed threshold lookback")
        if (
            not math.isfinite(self.shock_quantile)
            or not 0.0 < self.shock_quantile < 1.0
        ):
            raise ValueError("oil reversion shock quantile must be in (0, 1)")
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (self.target_bps, self.stop_bps)
        ):
            raise ValueError("oil reversion target and stop must be positive")
        if self.target_bps <= self.stop_bps:
            raise ValueError("oil reversion target must exceed stop distance")


def build_hip3_oil_shock_reversion_signals(
    bars: pd.DataFrame,
    config: Hip3OilShockReversionConfig = Hip3OilShockReversionConfig(),
) -> pd.DataFrame:
    """Return gap-reset, next-bar-eligible symmetric reversion instructions."""
    _validate_bars(bars)
    segments = bars["gap_before_bars"].gt(0).cumsum().astype(int)
    close = bars["close"].astype(float)
    trailing = (
        close.groupby(segments, sort=False)
        .pct_change(config.return_lookback_bars)
        .mul(10_000.0)
    )
    threshold = (
        trailing.abs()
        .groupby(segments, sort=False)
        .transform(
            lambda values: values.shift(1)
            .rolling(
                config.threshold_lookback_bars,
                min_periods=config.minimum_history_bars,
            )
            .quantile(config.shock_quantile)
        )
    )
    long_raw = trailing.lt(-threshold)
    short_raw = trailing.gt(threshold)
    long_entry = _fresh(long_raw, segments)
    short_entry = _fresh(short_raw, segments)
    return _signal_frame(
        bars.index,
        trailing,
        threshold,
        long_entry,
        short_entry,
        segments,
        bars["gap_before_bars"].gt(0),
    )


def _signal_frame(
    index: pd.DatetimeIndex,
    trailing: pd.Series,
    threshold: pd.Series,
    long_entry: pd.Series,
    short_entry: pd.Series,
    segments: pd.Series,
    recovery: pd.Series,
) -> pd.DataFrame:
    direction = pd.Series(None, index=index, dtype=object)
    direction.loc[long_entry] = "long"
    direction.loc[short_entry] = "short"
    output = pd.DataFrame(index=index)
    output["long_entry"] = long_entry.astype(bool)
    output["short_entry"] = short_entry.astype(bool)
    output["entry_direction"] = direction
    output["long_exit"] = short_entry.astype(bool) | recovery
    output["short_exit"] = long_entry.astype(bool) | recovery
    output["signal_name"] = direction.map(
        {
            "long": "hip3_oil_shock_reversion_long@5m",
            "short": "hip3_oil_shock_reversion_short@5m",
        }
    )
    output["target_price"] = float("nan")
    output["stop_price"] = float("nan")
    output["trailing_return_bps"] = trailing
    output["shock_threshold_bps"] = threshold
    output["source_segment_id"] = segments
    output["execution_authority"] = "none"
    return output


def _fresh(raw: pd.Series, segments: pd.Series) -> pd.Series:
    prior = raw.groupby(segments, sort=False).shift(1, fill_value=False)
    return raw.fillna(False) & ~prior.astype(bool)


def _validate_bars(bars: pd.DataFrame) -> None:
    missing = {"close", "gap_before_bars"}.difference(bars.columns)
    if missing:
        raise ValueError(f"oil reversion bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("oil reversion bars require timezone-aware timestamps")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("oil reversion bars require ordered unique rows")
