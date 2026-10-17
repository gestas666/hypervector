"""Shared paper bars contracts.

Offline multi-bar walk and incremental ``on_bar`` for the live daemon share
the same alpha path. No Nautilus node, no venue orders. Funding uses the
configured/last hourly rate offline; optional live refresh is opt-in.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Mapping

import pandas as pd


logger = logging.getLogger(__name__)
_OHLCV_REQUIRED = ("open", "high", "low", "close", "volume")


def _prepare_ohlcv(ohlcv: pd.DataFrame, *, max_bars: int | None) -> pd.DataFrame:
    if ohlcv is None or not isinstance(ohlcv, pd.DataFrame) or ohlcv.empty:
        raise ValueError("OHLCV must be a non-empty DataFrame")
    frame = ohlcv.copy()
    if "timestamp" not in frame.columns and frame.index.name == "timestamp":
        frame = frame.reset_index()
    missing = [c for c in _OHLCV_REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")
    if max_bars is not None:
        frame = frame.iloc[: int(max_bars)]
    return frame.reset_index(drop=True)


def _row_to_buffer_record(row: pd.Series) -> dict[str, Any]:
    ts = row["timestamp"] if "timestamp" in row.index else None
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        ts = pd.Timestamp.utcnow()
    else:
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    return {
        "timestamp": ts,
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
    }


def _buffer_to_df(buffer: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(buffer)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    return df.loc[:, list(_OHLCV_REQUIRED)].astype(float)


def _feed_ts(record: dict[str, Any]) -> str:
    ts = record.get("timestamp")
    if ts is None:
        return "unknown"
    if isinstance(ts, pd.Timestamp):
        return ts.isoformat()
    return str(ts)


def _timeframe_minutes(timeframe: str) -> int:
    values = {"1m": 1, "5m": 5, "15m": 15}
    if timeframe not in values:
        raise ValueError(f"unsupported funding timeframe: {timeframe}")
    return values[timeframe]


def _bar_close_timestamp(
    record: dict[str, Any],
    *,
    timeframe: str,
) -> pd.Timestamp:
    return pd.Timestamp(record["timestamp"]) + pd.Timedelta(
        minutes=_timeframe_minutes(timeframe)
    )


def _is_funding_boundary(
    record: dict[str, Any],
    *,
    timeframe: str,
) -> bool:
    closed_at = _bar_close_timestamp(record, timeframe=timeframe)
    return closed_at.minute == 0 and closed_at.second == 0


def _resume_timestamp(value: str) -> pd.Timestamp:
    """Parse an authoritative ledger timestamp or fail closed."""
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"invalid shadow portfolio state timestamp: {value!r}"
        ) from exc
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _bars_closing_after(
    frame: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    timeframe: str,
) -> pd.DataFrame:
    """Return timestamp-ordered bars whose close follows persisted state."""
    normalized = frame.copy()
    timestamps = pd.to_datetime(normalized["timestamp"], utc=True)
    normalized = normalized.assign(timestamp=timestamps).sort_values("timestamp")
    closes = normalized["timestamp"] + pd.Timedelta(
        minutes=_timeframe_minutes(timeframe)
    )
    return normalized.loc[closes > cutoff].reset_index(drop=True)


def _normalized_funding_rates(
    rates: Mapping[pd.Timestamp, float],
) -> dict[pd.Timestamp, float]:
    """Normalize historical funding keys to exact UTC timestamps."""
    normalized: dict[pd.Timestamp, float] = {}
    for raw_timestamp, raw_rate in rates.items():
        timestamp = pd.Timestamp(raw_timestamp)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        rate = float(raw_rate)
        if not math.isfinite(rate):
            raise RuntimeError(f"non-finite funding history at {timestamp.isoformat()}")
        normalized[timestamp] = rate
    return normalized
