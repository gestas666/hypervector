"""Live bar feed for paper daemon — public market data only.

No venue order client. Default path polls HL REST candles on an interval.

Each poll requests only the window that can contain new bars (two bars before
the last processed open through now, never more than the 1-day cap) over one
keep-alive HTTP session per poll function, and parses the candles in one
columnar pass. Gap filling belongs to warm-up, not to the steady-state poll.

TODO Phase3: prefer HyperliquidDataClient WS when stable.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
import pandas as pd
import requests

from hypervector.data.hl import HL_INFO_URL, bars_from_hl_payload, fetch_hl_ohlcv, hl_coin
from hypervector.data.provenance import normalize_ohlcv

# Default poll cadence for REST fallback (seconds).
DEFAULT_POLL_INTERVAL_SECS = 5.0

# Upper bound of the window for each REST poll (days); 1 day covers catch-up.
_POLL_LOOKBACK_DAYS = 1
# One candleSnapshot response holds at most 5000 candles; stay well below it.
_MAX_SINGLE_REQUEST_CANDLES = 4800
_MILLIS_PER_DAY = 86_400_000


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


def candles_from_hl_payload(
    raw: list[dict[str, Any]], *, source: str = "hl"
) -> pd.DataFrame:
    """Columnar equivalent of :func:`bars_from_hl_payload` for poll responses.

    Values use the same Python ``int``/``float`` conversions and one vectorized
    timestamp conversion. Any malformed row falls back to the reference
    per-row parser so skip semantics stay identical.
    """
    if not raw:
        return bars_from_hl_payload(raw, source=source)
    try:
        times = np.fromiter(
            (int(item["t"]) for item in raw), dtype=np.int64, count=len(raw)
        )
        columns = {
            name: [float(item[key]) for item in raw]
            for name, key in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"))
        }
        volume = [float(item.get("v") or 0.0) for item in raw]
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return bars_from_hl_payload(raw, source=source)
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(times, unit="ms", utc=True),
            **columns,
            "volume": volume,
            "source": source,
        }
    )
    return normalize_ohlcv(frame, source=source)


def _fetch_bounded_candles(
    symbol: str,
    timeframe: str,
    *,
    start_ms: int,
    end_ms: int,
    session: Any,
) -> pd.DataFrame:
    """One public candleSnapshot request for ``[start_ms, end_ms]`` (no retry)."""
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": hl_coin(symbol),
            "interval": timeframe,
            "startTime": int(start_ms),
            "endTime": int(end_ms),
        },
    }
    response = session.post(HL_INFO_URL, json=payload, timeout=30)
    response.raise_for_status()
    raw = response.json()
    if not isinstance(raw, list):
        raise RuntimeError("HL candleSnapshot response must be a list")
    frame = candles_from_hl_payload(raw, source="hl")
    if frame.empty:
        return frame
    within = (frame["timestamp"] >= pd.to_datetime(start_ms, unit="ms", utc=True)) & (
        frame["timestamp"] <= pd.to_datetime(end_ms, unit="ms", utc=True)
    )
    return frame.loc[within].drop_duplicates(subset=["timestamp"]).reset_index(drop=True)


def fetch_new_hl_bars(
    symbol: str,
    timeframe: str,
    *,
    after_ts: pd.Timestamp | None = None,
    lookback_days: float = _POLL_LOOKBACK_DAYS,
    session: Any | None = None,
    end_ms: int | None = None,
) -> pd.DataFrame:
    """Poll public HL candleSnapshot and return bars strictly after ``after_ts``.

    Uses REST only (no API key). Empty frame if nothing new. A window that fits
    one response is fetched with a single request; longer windows use the
    chunked :func:`fetch_hl_ohlcv` walk.
    """
    # TODO Phase3: prefer HyperliquidDataClient WS when stable
    end = int(end_ms) if end_ms is not None else int(time.time() * 1000)
    window_ms = int(float(lookback_days) * _MILLIS_PER_DAY)
    step_ms = int(timeframe_delta(timeframe) / pd.Timedelta(milliseconds=1))
    if window_ms // step_ms + 1 <= _MAX_SINGLE_REQUEST_CANDLES:
        df = _fetch_bounded_candles(
            symbol,
            timeframe,
            start_ms=end - window_ms,
            end_ms=end,
            session=session if session is not None else requests.Session(),
        )
    else:
        df = fetch_hl_ohlcv(
            symbol, timeframe, lookback_days, session=session, end_ms=end
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


def poll_window(
    timeframe: str,
    *,
    after_ts: pd.Timestamp | None,
    now: pd.Timestamp,
    lookback_days: float = _POLL_LOOKBACK_DAYS,
) -> pd.Timedelta:
    """Return the REST window that can hold every bar after ``after_ts``.

    Without an anchor the full cap is used. With one, the window starts two
    bars before ``after_ts`` (at least three bars long) and never exceeds the
    cap, so catch-up returns the same rows as a full-cap poll.
    """
    cap = pd.Timedelta(days=lookback_days)
    if after_ts is None:
        return cap
    step = timeframe_delta(timeframe)
    gap = _utc_timestamp(now) - _utc_timestamp(after_ts) + 2 * step
    return min(max(gap, 3 * step), cap)


def make_rest_poll_fn(
    symbol: str,
    timeframe: str,
    *,
    lookback_days: float = _POLL_LOOKBACK_DAYS,
    session: Any | None = None,
    now_fn: Callable[[], pd.Timestamp] | None = None,
) -> Callable[..., pd.DataFrame]:
    """Build a poll_fn(after_ts=...) suitable for :func:`start_paper_daemon`.

    The poll function owns one keep-alive ``requests.Session`` (the daemon loop
    is single-threaded) unless a session is injected.
    """
    sess = session if session is not None else requests.Session()
    clock = now_fn if now_fn is not None else (lambda: pd.Timestamp.now(tz="UTC"))

    def _poll(*, after_ts: pd.Timestamp | None = None, **_kwargs: Any) -> pd.DataFrame:
        now = _utc_timestamp(clock())
        window = poll_window(
            timeframe, after_ts=after_ts, now=now, lookback_days=lookback_days
        )
        return fetch_new_hl_bars(
            symbol,
            timeframe,
            after_ts=after_ts,
            lookback_days=window / pd.Timedelta(days=1),
            session=sess,
            end_ms=int(now.value // 1_000_000),
        )

    return _poll
