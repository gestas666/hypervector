"""Shared causal candle preparation for SOL shadow and live decisions."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from hypervector.regime.classifier import validate_regime_bars

_MINUTE = pd.Timedelta(minutes=1)
_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def index_range_onset_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Return sorted, unique, UTC-indexed SOL OHLCV bars."""
    required = {"timestamp", *_OHLCV_COLUMNS}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"SOL candle frame is missing columns: {sorted(missing)}")
    result = frame.loc[:, sorted(required)].copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    result = result.drop_duplicates("timestamp", keep="last").set_index("timestamp")
    return result.sort_index().loc[:, list(_OHLCV_COLUMNS)]


def prepare_completed_range_onset_frames(
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    signal_builder: Callable[[pd.DataFrame], pd.DataFrame],
    regime_builder: Callable[[pd.DataFrame], pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build signals and regimes using completed one-minute bars only."""
    complete = completed_range_onset_bars(raw_bars, observed_at=observed_at)
    return complete, signal_builder(complete), regime_builder(complete)


def completed_range_onset_bars(
    raw_bars: pd.DataFrame, *, observed_at: pd.Timestamp
) -> pd.DataFrame:
    """Validate and retain the latest contiguous completed minute segment."""
    bars = index_range_onset_bars(raw_bars)
    observed = _utc_timestamp(observed_at)
    complete = bars.loc[bars.index + _MINUTE <= observed]
    if complete.empty:
        raise ValueError("Hyperliquid returned no completed SOL candles")
    complete = _latest_contiguous_segment(complete)
    if not complete.index.floor("min").equals(complete.index):
        raise ValueError("1m regime bars require exact 1m open-time cadence")
    validate_regime_bars(complete)
    return complete


def _latest_contiguous_segment(complete: pd.DataFrame) -> pd.DataFrame:
    deltas = complete.index[1:] - complete.index[:-1]
    resets = [position + 1 for position, delta in enumerate(deltas) if delta != _MINUTE]
    return complete.iloc[resets[-1] :] if resets else complete


def _utc_timestamp(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("observer timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")
