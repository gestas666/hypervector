"""Causal funding-extreme and price-exhaustion signal primitives."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.research.hype_impulse_5m_signals import validate_five_minute_bars


@dataclass(frozen=True)
class FundingPriceExhaustionConfig:
    """Frozen causal thresholds for an asset-specific report-only screen."""

    funding_lookback_events: int = 720
    minimum_funding_history_events: int = 168
    lower_funding_quantile: float = 0.05
    upper_funding_quantile: float = 0.95
    minimum_previous_extension_bps: float = 60.0
    clean_history_bars: int = 60

    def __post_init__(self) -> None:
        """Reject settings that weaken causal history or signal symmetry."""
        if self.funding_lookback_events < 4:
            raise ValueError("funding lookback must contain at least four events")
        minimum = self.minimum_funding_history_events
        if not 4 <= minimum <= self.funding_lookback_events:
            raise ValueError("minimum funding history must be within the lookback")
        if not 0.0 < self.lower_funding_quantile < 0.5:
            raise ValueError("lower funding quantile must be between zero and 0.5")
        if not 0.5 < self.upper_funding_quantile < 1.0:
            raise ValueError("upper funding quantile must be between 0.5 and one")
        extension = self.minimum_previous_extension_bps
        if not math.isfinite(extension) or extension <= 0.0:
            raise ValueError("minimum previous extension must be finite and positive")
        if self.clean_history_bars < 21:
            raise ValueError("clean history must cover the 21-bar EMA")


@dataclass(frozen=True)
class FundingPriceExhaustionSignals:
    """Aligned signals, ATR distances, and point-in-time diagnostics."""

    long_signals: pd.Series
    short_signals: pd.Series
    atr_bps: pd.Series
    diagnostics: pd.DataFrame


def build_funding_price_exhaustion_signals(
    bars: pd.DataFrame,
    funding: pd.DataFrame,
    config: FundingPriceExhaustionConfig | None = None,
) -> FundingPriceExhaustionSignals:
    """Build onset-only reversal signals from completed bars and known funding."""
    cfg = config or FundingPriceExhaustionConfig()
    frame = validate_five_minute_bars(bars)
    _validate_prices(frame)
    funding_state = _funding_state(funding, cfg)
    diagnostics = _diagnostics(frame, funding_state, cfg)
    long_condition = _condition(diagnostics, cfg, "long")
    short_condition = _condition(diagnostics, cfg, "short")
    return FundingPriceExhaustionSignals(
        _onset(long_condition),
        _onset(short_condition),
        _atr_bps(frame),
        diagnostics,
    )


def _funding_state(
    funding: pd.DataFrame, config: FundingPriceExhaustionConfig
) -> pd.DataFrame:
    required = {"timestamp", "event_ts_ms", "funding_rate", "source"}
    missing = sorted(required - set(funding.columns))
    if missing:
        raise ValueError(f"funding rows missing columns: {missing}")
    frame = funding.loc[:, sorted(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.as_unit("ns")
    frame["available_at"] = pd.to_datetime(
        frame["event_ts_ms"], unit="ms", utc=True
    ).dt.as_unit("ns")
    _validate_funding_rows(frame)
    rates = frame["funding_rate"].astype(float) * 10_000.0
    frame["funding_rate_bps"] = rates
    prior = rates.shift(1).rolling(
        config.funding_lookback_events,
        min_periods=config.minimum_funding_history_events,
    )
    frame["lower_funding_threshold_bps"] = prior.quantile(config.lower_funding_quantile)
    frame["upper_funding_threshold_bps"] = prior.quantile(config.upper_funding_quantile)
    return frame


def _validate_funding_rows(frame: pd.DataFrame) -> None:
    available = pd.DatetimeIndex(frame["available_at"])
    semantic = pd.DatetimeIndex(frame["timestamp"])
    if available.hasnans or available.has_duplicates:
        raise ValueError("funding availability timestamps must be ordered and unique")
    if not available.is_monotonic_increasing:
        raise ValueError("funding availability timestamps must be ordered and unique")
    if (
        semantic.hasnans
        or semantic.has_duplicates
        or not semantic.is_monotonic_increasing
    ):
        raise ValueError("funding timestamps must be ordered and unique")
    if (available < semantic).any():
        raise ValueError("funding cannot be available before its event timestamp")
    if not frame["source"].astype(str).eq("hl_funding_history").all():
        raise ValueError("funding source must be hl_funding_history")
    if not np.isfinite(frame["funding_rate"].to_numpy(float)).all():
        raise ValueError("funding rates must be finite")


def _diagnostics(
    frame: pd.DataFrame,
    funding: pd.DataFrame,
    config: FundingPriceExhaustionConfig,
) -> pd.DataFrame:
    output = frame.loc[:, ["timestamp", "open", "close"]].copy()
    output["bar_close_at"] = (output["timestamp"] + pd.Timedelta(minutes=5)).dt.as_unit(
        "ns"
    )
    state_columns = [
        "available_at",
        "funding_rate_bps",
        "lower_funding_threshold_bps",
        "upper_funding_threshold_bps",
    ]
    output = pd.merge_asof(
        output.sort_values("bar_close_at"),
        funding.loc[:, state_columns],
        left_on="bar_close_at",
        right_on="available_at",
        direction="backward",
    )
    ema21 = frame["close"].ewm(span=21, adjust=False, min_periods=21).mean()
    output["ema21"] = ema21
    output["previous_extension_bps"] = (
        (frame["close"] / ema21 - 1.0) * 10_000.0
    ).shift(1)
    output["clean_history"] = _clean_history(
        frame["contains_gap_fill"], config.clean_history_bars
    )
    return output.reset_index(drop=True)


def _condition(
    frame: pd.DataFrame, config: FundingPriceExhaustionConfig, side: str
) -> pd.Series:
    funding = frame["funding_rate_bps"]
    extension = frame["previous_extension_bps"]
    previous_close = frame["close"].shift(1)
    if side == "long":
        extreme = funding.lt(0.0) & funding.le(frame["lower_funding_threshold_bps"])
        extended = extension.le(-config.minimum_previous_extension_bps)
        reversal = frame["close"].gt(frame["open"]) & frame["close"].gt(previous_close)
    else:
        extreme = funding.gt(0.0) & funding.ge(frame["upper_funding_threshold_bps"])
        extended = extension.ge(config.minimum_previous_extension_bps)
        reversal = frame["close"].lt(frame["open"]) & frame["close"].lt(previous_close)
    return (frame["clean_history"] & extreme & extended & reversal).fillna(False)


def _onset(condition: pd.Series) -> pd.Series:
    return (condition & ~condition.shift(1, fill_value=False)).astype(bool)


def _clean_history(gaps: pd.Series, bars: int) -> pd.Series:
    return gaps.astype(int).rolling(bars, min_periods=bars).sum().eq(0)


def _atr_bps(frame: pd.DataFrame) -> pd.Series:
    previous = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous).abs(),
            (frame["low"] - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return (atr / frame["close"]) * 10_000.0


def _validate_prices(frame: pd.DataFrame) -> None:
    columns = ["open", "high", "low", "close", "volume"]
    if not np.isfinite(frame.loc[:, columns].to_numpy(float)).all():
        raise ValueError("funding-exhaustion bars must be finite")
    prices = frame.loc[:, ["open", "high", "low", "close"]].to_numpy(float)
    if (prices <= 0.0).any():
        raise ValueError("funding-exhaustion prices must be positive")
    if (frame["volume"].to_numpy(float) < 0.0).any():
        raise ValueError("funding-exhaustion volume must be non-negative")
