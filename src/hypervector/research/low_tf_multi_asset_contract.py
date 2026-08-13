"""Frozen data and timing contract for bidirectional low-timeframe research."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Literal

import numpy as np
import pandas as pd

SegmentName = Literal["development", "validation", "pseudo_holdout"]

_OHLCV = ("open", "high", "low", "close", "volume")
_SEGMENTS: tuple[tuple[SegmentName, str, str], ...] = (
    ("development", "2025-07-28", "2026-01-28"),
    ("validation", "2026-01-28", "2026-04-28"),
    ("pseudo_holdout", "2026-04-28", "2026-07-28"),
)


@dataclass(frozen=True)
class LowTfAssetSpec:
    """Immutable native-perpetual symbol and documented leverage ceiling."""

    symbol: str
    venue_max_leverage: float

    def __post_init__(self) -> None:
        """Reject malformed or non-positive asset metadata."""
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("asset symbol must be non-empty uppercase text")
        _positive(self.venue_max_leverage, "venue_max_leverage")


@dataclass(frozen=True)
class LowTfResearchContract:
    """Frozen experiment dimensions, portfolio assumptions, and time windows."""

    assets: tuple[LowTfAssetSpec, ...]
    execution_minutes: int = 5
    context_minutes: int = 15
    initial_equity_usd: float = 15_000.0
    leverage: float = 5.0
    risk_fraction_per_trade: float = 0.005
    maximum_open_risk_fraction: float = 0.01
    maximum_positions: int = 2
    nominal_round_trip_cost_bps: float = 13.0
    stress_round_trip_cost_bps: float = 20.0

    def __post_init__(self) -> None:
        """Reject internally inconsistent experiment settings."""
        if not self.assets or len({asset.symbol for asset in self.assets}) != len(
            self.assets
        ):
            raise ValueError("research assets must be non-empty and unique")
        _positive_integer(self.execution_minutes, "execution_minutes")
        _positive_integer(self.context_minutes, "context_minutes")
        if self.context_minutes % self.execution_minutes:
            raise ValueError("context_minutes must be a multiple of execution_minutes")
        _positive(self.initial_equity_usd, "initial_equity_usd")
        _positive(self.leverage, "leverage")
        if any(self.leverage > asset.venue_max_leverage for asset in self.assets):
            raise ValueError("research leverage exceeds an asset venue maximum")
        _fraction(self.risk_fraction_per_trade, "risk_fraction_per_trade")
        _fraction(self.maximum_open_risk_fraction, "maximum_open_risk_fraction")
        if self.maximum_open_risk_fraction < self.risk_fraction_per_trade:
            raise ValueError("maximum open risk must cover at least one trade")
        _positive_integer(self.maximum_positions, "maximum_positions")
        _positive(self.nominal_round_trip_cost_bps, "nominal cost")
        _positive(self.stress_round_trip_cost_bps, "stress cost")
        if self.stress_round_trip_cost_bps < self.nominal_round_trip_cost_bps:
            raise ValueError("stress cost must not be below nominal cost")

    def segment(self, name: SegmentName) -> tuple[pd.Timestamp, pd.Timestamp]:
        """Return the half-open UTC boundaries for a declared segment."""
        for segment_name, start, end in _SEGMENTS:
            if segment_name == name:
                return pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
        raise ValueError(f"unknown low-timeframe segment: {name}")


def default_low_tf_contract() -> LowTfResearchContract:
    """Return the predeclared native-asset research contract."""
    assets = (
        LowTfAssetSpec("BTC", 40.0),
        LowTfAssetSpec("ETH", 25.0),
        LowTfAssetSpec("SOL", 20.0),
        LowTfAssetSpec("HYPE", 10.0),
    )
    return LowTfResearchContract(assets=assets)


def complete_ohlcv_bars(
    bars: pd.DataFrame,
    *,
    source_minutes: int,
    bar_minutes: int,
) -> pd.DataFrame:
    """Aggregate ordered source bars and retain only complete UTC buckets."""
    _validate_duration(source_minutes, bar_minutes)
    frame = _validated_ohlcv(bars)
    expected_count = bar_minutes // source_minutes
    indexed = frame.set_index("timestamp")
    grouped = indexed.resample(f"{bar_minutes}min", label="left", closed="left")
    result = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        constituent_bars=("close", "count"),
    )
    result = result.loc[result["constituent_bars"].eq(expected_count)]
    return (
        result.drop(columns="constituent_bars").rename_axis("bar_open_at").reset_index()
    )


def scored_segment(
    bars: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Return scored rows inside a half-open interval while retaining warmup."""
    times = _validated_times(bars, "bar_open_at")
    start_value = _aware_timestamp(start, "start")
    end_value = _aware_timestamp(end, "end")
    if start_value >= end_value:
        raise ValueError("scored segment start must precede end")
    selected = (times >= start_value) & (times < end_value)
    return bars.loc[selected].copy().reset_index(drop=True)


def ordered_frame_sha256(frame: pd.DataFrame, *, time_column: str) -> str:
    """Hash ordered labels, dtypes, index, and values for evidence identity."""
    _validated_times(frame, time_column)
    digest = sha256()
    digest.update(json.dumps([str(value) for value in frame.columns]).encode())
    digest.update(json.dumps([str(value) for value in frame.dtypes]).encode())
    hashed = pd.util.hash_pandas_object(frame, index=True).to_numpy()
    digest.update(hashed.tobytes())
    return digest.hexdigest()


def _validated_ohlcv(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", *_OHLCV}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"low-timeframe OHLCV missing columns: {missing}")
    _validated_times(bars, "timestamp")
    frame = bars.loc[:, ["timestamp", *_OHLCV]].copy()
    values = frame.loc[:, list(_OHLCV)].to_numpy(dtype=np.float64)
    if frame.empty or not np.isfinite(values).all():
        raise ValueError("low-timeframe OHLCV must be finite and non-empty")
    if (values[:, :4] <= 0.0).any() or (values[:, 4] < 0.0).any():
        raise ValueError("prices must be positive and volume non-negative")
    return frame


def _validated_times(frame: pd.DataFrame, column: str) -> pd.DatetimeIndex:
    if column not in frame:
        raise ValueError(f"time column is missing: {column}")
    times = pd.DatetimeIndex(frame[column])
    if times.tz is None:
        raise ValueError(f"{column} must be timezone-aware")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError(f"{column} must be ordered and unique")
    return times


def _validate_duration(source_minutes: int, bar_minutes: int) -> None:
    _positive_integer(source_minutes, "source_minutes")
    if isinstance(bar_minutes, bool) or not isinstance(bar_minutes, int):
        raise ValueError("bar_minutes must be a positive multiple of source_minutes")
    if bar_minutes <= 0 or bar_minutes % source_minutes:
        raise ValueError("bar_minutes must be a positive multiple of source_minutes")


def _aware_timestamp(value: pd.Timestamp, name: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f"{name} must be timezone-aware")
    return timestamp


def _positive(value: float, name: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
        raise ValueError(f"{name} must be positive and finite")


def _positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _fraction(value: float, name: str) -> None:
    _positive(value, name)
    if value > 1.0:
        raise ValueError(f"{name} must not exceed one")
