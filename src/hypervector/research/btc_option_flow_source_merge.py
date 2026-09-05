"""Deterministic merge rules for bound BTC option-flow market sources."""

from __future__ import annotations

from collections.abc import Sequence
import math

import pandas as pd

from hypervector.data.provenance import OHLCV_COLUMNS, normalize_ohlcv


def merge_option_flow_candles(
    frames: Sequence[pd.DataFrame],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Merge exact-overlap candle bundles without selecting a preferred source."""
    start_at, end_at = _bounds(start, end)
    if not frames:
        raise ValueError("option-flow candle merge requires source frames")
    merged = pd.concat(
        [normalize_ohlcv(frame) for frame in frames], ignore_index=True
    ).sort_values("timestamp")
    if _conflicting_duplicates(merged, OHLCV_COLUMNS[1:]):
        raise ValueError("option-flow source has conflicting duplicate candles")
    output = merged.drop_duplicates("timestamp", keep="first")
    output = output.loc[
        output["timestamp"].ge(start_at) & output["timestamp"].lt(end_at)
    ].reset_index(drop=True)
    if output.empty or output["timestamp"].duplicated().any():
        raise ValueError("option-flow candle merge produced no unique observations")
    return output


def merge_option_flow_funding(
    frames: Sequence[pd.DataFrame],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Merge exact-overlap funding bundles into one complete hourly series."""
    start_at, end_at = _bounds(start, end)
    if not frames:
        raise ValueError("option-flow funding merge requires source frames")
    normalized = [_funding_frame(frame) for frame in frames]
    merged = pd.concat(normalized, ignore_index=True).sort_values("timestamp")
    if _conflicting_duplicates(merged, ("funding_rate",)):
        raise ValueError("option-flow source has conflicting duplicate funding")
    output = merged.drop_duplicates("timestamp", keep="first")
    output = output.loc[
        output["timestamp"].ge(start_at) & output["timestamp"].lt(end_at)
    ]
    expected = pd.date_range(start_at, end_at, freq="1h", inclusive="left")
    timestamps = pd.DatetimeIndex(output["timestamp"])
    if not timestamps.equals(expected):
        raise ValueError("option-flow funding merge lacks exact hourly coverage")
    return pd.Series(
        output["funding_rate"].to_numpy(dtype=float),
        index=expected,
        name="funding_rate",
    )


def _funding_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "funding_rate"}
    if required.difference(frame.columns):
        raise ValueError("option-flow funding frame lacks required columns")
    output = frame.loc[:, ["timestamp", "funding_rate"]].copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True)
    output["funding_rate"] = pd.to_numeric(
        output["funding_rate"], errors="raise"
    ).astype(float)
    if (
        output["timestamp"].isna().any()
        or not output["funding_rate"].map(math.isfinite).all()
    ):
        raise ValueError("option-flow funding contains invalid values")
    return output


def _conflicting_duplicates(frame: pd.DataFrame, value_columns: Sequence[str]) -> bool:
    duplicates = frame.loc[frame["timestamp"].duplicated(keep=False)]
    if duplicates.empty:
        return False
    variations = duplicates.groupby("timestamp", sort=False)[
        list(value_columns)
    ].nunique(dropna=False)
    return bool(variations.gt(1).any(axis=None))


def _bounds(
    start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_at, end_at = pd.Timestamp(start), pd.Timestamp(end)
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise ValueError("option-flow merge bounds must be timezone-aware")
    start_at, end_at = start_at.tz_convert("UTC"), end_at.tz_convert("UTC")
    if start_at != start_at.floor("h") or end_at != end_at.floor("h"):
        raise ValueError("option-flow merge bounds must be hour-aligned")
    if start_at >= end_at:
        raise ValueError("option-flow merge bounds must be increasing")
    return start_at, end_at
