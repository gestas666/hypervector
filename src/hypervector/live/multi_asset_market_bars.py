"""Validated completed-candle handling for the multi-asset live cohort."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

import pandas as pd

_INTERVAL_MINUTES = {"1m": 1, "5m": 5}
_MAX_CHART_BARS = 360


class MultiAssetIntentPollerError(RuntimeError):
    """Cohort candle polling could not preserve causal provider boundaries."""


class TransientCohortMarketDataError(MultiAssetIntentPollerError):
    """An exhausted but retryable public market-data read skipped one cycle."""

    def __init__(self, *, source: str, reason: str) -> None:
        if not source.strip() or not reason.strip():
            raise ValueError("transient market-data source and reason are required")
        self.source = source.strip()
        self.reason = reason.strip()
        super().__init__(f"{self.source}: {self.reason}")


@dataclass(frozen=True)
class CohortMarketBar:
    """One completed venue candle published to read-only cohort telemetry."""

    symbol: str
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        """Reject invalid or structurally impossible OHLCV values."""
        prices = (self.open, self.high, self.low, self.close)
        if not self.symbol or self.timestamp_ms < 0:
            raise MultiAssetIntentPollerError("market bar identity is invalid")
        if any(not math.isfinite(value) or value <= 0.0 for value in prices):
            raise MultiAssetIntentPollerError("market bar prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            raise MultiAssetIntentPollerError("market bar OHLC range is invalid")
        if self.low > self.high:
            raise MultiAssetIntentPollerError("market bar low exceeds high")
        if not math.isfinite(self.volume) or self.volume < 0.0:
            raise MultiAssetIntentPollerError("market bar volume is invalid")


def merge_one_minute_bars(
    cached: pd.DataFrame | None,
    fresh: pd.DataFrame,
    observed_ms: int,
    retention_days: int,
) -> pd.DataFrame:
    """Merge an incremental venue window into the bounded causal cache."""
    frames = [fresh] if cached is None else [cached, fresh]
    merged = pd.concat(frames, ignore_index=True)
    if "timestamp" not in merged.columns:
        raise MultiAssetIntentPollerError("source bars missing timestamp")
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True, errors="raise")
    start = pd.to_datetime(
        observed_ms - retention_days * 24 * 60 * 60 * 1_000,
        unit="ms",
        utc=True,
    )
    return (
        merged.loc[merged["timestamp"].ge(start)]
        .sort_values("timestamp", kind="stable")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )


def resample_one_minute_to_five(bars: pd.DataFrame) -> pd.DataFrame:
    """Build complete causal five-minute bars from the shared minute feed."""
    return resample_one_minute_bars(bars, minutes=5)


def resample_one_minute_bars(
    bars: pd.DataFrame,
    *,
    minutes: int,
) -> pd.DataFrame:
    """Build complete causal fixed-minute bars from the shared minute feed."""
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
        raise MultiAssetIntentPollerError("resample minutes must be positive")
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise MultiAssetIntentPollerError(f"source bars missing columns: {missing}")
    indexed = bars.loc[:, sorted(required)].set_index("timestamp")
    grouped = indexed.resample(f"{minutes}min", label="left", closed="left")
    output = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_bars=("close", "count"),
    )
    complete = output.loc[output["source_bars"].eq(minutes)].drop(columns="source_bars")
    return complete.reset_index()


def latest_completed_price(
    bars: pd.DataFrame,
    observed: pd.Timestamp,
    timeframe: str,
) -> float:
    """Return the latest completed positive close for a source timeframe."""
    complete = _completed_bars(bars, observed, timeframe, {"timestamp", "close"})
    value = float(complete.iloc[-1]["close"])
    if not math.isfinite(value) or value <= 0.0:
        raise MultiAssetIntentPollerError("completed reference price is invalid")
    return value


def completed_market_bars(
    bars: pd.DataFrame,
    observed: pd.Timestamp,
    symbol: str,
    *,
    limit: int = _MAX_CHART_BARS,
) -> tuple[CohortMarketBar, ...]:
    """Project the bounded completed minute history used by cohort charts."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise MultiAssetIntentPollerError("completed market bar limit must be positive")
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    complete = _completed_bars(bars, observed, "1m", required).tail(limit)
    return tuple(
        CohortMarketBar(
            symbol=symbol,
            timestamp_ms=int(pd.Timestamp(row.timestamp).timestamp() * 1_000),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in complete.itertuples(index=False)
    )


def aware_utc(value: datetime) -> pd.Timestamp:
    """Normalize an aware cohort clock to UTC without inventing a timezone."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise MultiAssetIntentPollerError("cohort clock must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _completed_bars(
    bars: pd.DataFrame,
    observed: pd.Timestamp,
    timeframe: str,
    required: set[str],
) -> pd.DataFrame:
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise MultiAssetIntentPollerError(f"source bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise MultiAssetIntentPollerError(
            "source timestamps must be aware, unique, and increasing"
        )
    interval = pd.Timedelta(minutes=_INTERVAL_MINUTES[timeframe])
    complete = bars.loc[times + interval <= observed]
    if complete.empty:
        raise MultiAssetIntentPollerError("source has no completed reference bar")
    return complete
