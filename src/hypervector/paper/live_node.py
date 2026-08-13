"""Live bar feed for paper daemon — public market data only.

No venue order client. Default path polls HL REST candles on an interval.

TODO Phase3: prefer HyperliquidDataClient WS when stable.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from hypervector.data.hl import fetch_hl_ohlcv

# Default poll cadence for REST fallback (seconds).
DEFAULT_POLL_INTERVAL_SECS = 5.0

# Lookback window for each REST poll (days) — small tail is enough for new bars.
_POLL_LOOKBACK_DAYS = 1


def timeframe_delta(timeframe: str) -> pd.Timedelta:
    """Return the supported candle duration or fail on an unknown timeframe."""
    durations = {
        "1m": pd.Timedelta(minutes=1),
        "5m": pd.Timedelta(minutes=5),
        "15m": pd.Timedelta(minutes=15),
        "1h": pd.Timedelta(hours=1),
    }
    try:
        return durations[timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported live timeframe: {timeframe}") from exc


def partition_live_bars(
    frame: pd.DataFrame,
    *,
    timeframe: str,
    activated_at: pd.Timestamp,
    observed_at: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split completed bars into pre-activation seed and genuine live bars.

    Candle timestamps are opens. A bar is complete only when its close is not
    later than ``observed_at``. Bars closing at or before activation are seed
    history and must never pass through execution.
    """
    activation = _utc_timestamp(activated_at)
    observed = _utc_timestamp(observed_at)
    completed = completed_bars_at(
        frame,
        timeframe=timeframe,
        observed_at=observed,
    )
    if completed.empty:
        return completed.copy(), completed.copy()
    closes = completed["timestamp"] + timeframe_delta(timeframe)
    completed_closes = closes.loc[completed.index]
    catchup = completed.loc[completed_closes <= activation].reset_index(drop=True)
    live = completed.loc[completed_closes > activation].reset_index(drop=True)
    return catchup, live


def completed_bars_at(
    frame: pd.DataFrame,
    *,
    timeframe: str,
    observed_at: pd.Timestamp,
) -> pd.DataFrame:
    """Return only candles causally complete at one observation timestamp."""
    normalized = filter_bars_after(frame, after_ts=None)
    if normalized.empty:
        return normalized.copy()
    observed = _utc_timestamp(observed_at)
    closes = normalized["timestamp"] + timeframe_delta(timeframe)
    return normalized.loc[closes <= observed].copy()


def _utc_timestamp(value: pd.Timestamp) -> pd.Timestamp:
    """Normalize one timestamp to UTC."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def fetch_new_hl_bars(
    symbol: str,
    timeframe: str,
    *,
    after_ts: pd.Timestamp | None = None,
    lookback_days: int = _POLL_LOOKBACK_DAYS,
    session: Any | None = None,
) -> pd.DataFrame:
    """Poll public HL candleSnapshot and return bars strictly after ``after_ts``.

    Uses REST only (no API key). Empty frame if nothing new.
    """
    # TODO Phase3: prefer HyperliquidDataClient WS when stable
    df = fetch_hl_ohlcv(
        symbol,
        timeframe,
        lookback_days,
        session=session,
    )
    return filter_bars_after(df, after_ts=after_ts)


def filter_bars_after(
    df: pd.DataFrame,
    *,
    after_ts: pd.Timestamp | None,
) -> pd.DataFrame:
    """Return OHLCV rows with timestamp > after_ts (all rows if after_ts is None)."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        if df is None:
            return pd.DataFrame(
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "source",
                ]
            )
        return df.copy()

    frame = df.copy()
    if "timestamp" not in frame.columns and frame.index.name == "timestamp":
        frame = frame.reset_index()
    if "timestamp" not in frame.columns:
        return frame.iloc[0:0].copy()

    ts = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.assign(timestamp=ts)
    if after_ts is None:
        return frame.reset_index(drop=True)

    cutoff = pd.Timestamp(after_ts)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    return frame.loc[ts > cutoff].reset_index(drop=True)


def make_rest_poll_fn(
    symbol: str,
    timeframe: str,
    *,
    lookback_days: int = _POLL_LOOKBACK_DAYS,
) -> Callable[..., pd.DataFrame]:
    """Build a poll_fn(after_ts=...) suitable for :func:`start_paper_daemon`."""

    def _poll(*, after_ts: pd.Timestamp | None = None, **_kwargs: Any) -> pd.DataFrame:
        return fetch_new_hl_bars(
            symbol,
            timeframe,
            after_ts=after_ts,
            lookback_days=lookback_days,
        )

    return _poll
