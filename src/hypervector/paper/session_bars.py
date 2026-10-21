"""Bar normalization, buffer and funding-boundary helpers for paper sessions.

Pure functions over OHLCV rows shared by :mod:`hypervector.paper.session` and
the live session: frame preparation, the rolling indicator buffer, candle
close timestamps, and hourly Hyperliquid funding boundaries.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

_OHLCV_REQUIRED = ("open", "high", "low", "close", "volume")
# Candle durations whose closes can be tested against hourly funding. Funding is
# charged one hour per boundary, so durations above one hour are unsupported.
_FUNDING_TIMEFRAME_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}


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
    if timeframe not in _FUNDING_TIMEFRAME_MINUTES:
        raise ValueError(f"unsupported funding timeframe: {timeframe}")
    return _FUNDING_TIMEFRAME_MINUTES[timeframe]


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
