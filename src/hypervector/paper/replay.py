"""Deterministic input preparation for shadow downtime reconciliation."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from hypervector.paper.live_node import timeframe_delta

_FUNDING_SETTLEMENT_QUERY_GRACE = pd.Timedelta(minutes=1)


class FundingHistoryFetcher(Protocol):
    """Callable interface for time-bounded public funding history."""

    def __call__(
        self,
        symbol: str,
        *,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> pd.DataFrame:
        """Return venue-identified funding observations for the interval."""
        ...


def split_resume_history(
    frame: pd.DataFrame,
    *,
    state_asof: str,
    timeframe: str,
    observed_at: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split seed bars from completed bars following persisted market state."""
    normalized = frame.copy()
    timestamps = pd.to_datetime(normalized["timestamp"], utc=True)
    normalized = normalized.assign(timestamp=timestamps).sort_values("timestamp")
    cutoff = _utc_timestamp(state_asof)
    observed = _utc_timestamp(observed_at)
    closes = normalized["timestamp"] + timeframe_delta(timeframe)
    seed = normalized.loc[closes <= cutoff].reset_index(drop=True)
    replay = normalized.loc[(closes > cutoff) & (closes <= observed)].reset_index(
        drop=True
    )
    return seed, replay


def historical_funding_rates(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    fetcher: FundingHistoryFetcher,
) -> dict[pd.Timestamp, float]:
    """Fetch exact public rates needed by hourly boundaries in replay bars."""
    if frame.empty:
        return {}
    if "source" not in frame or not frame["source"].eq("hl").all():
        raise RuntimeError("downtime reconciliation requires Hyperliquid bars")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    closes = timestamps + timeframe_delta(timeframe)
    boundaries = closes.loc[(closes.dt.minute == 0) & (closes.dt.second == 0)]
    if boundaries.empty:
        return {}
    history = fetcher(
        symbol,
        start_time=pd.Timestamp(boundaries.min()),
        end_time=pd.Timestamp(boundaries.max()) + _FUNDING_SETTLEMENT_QUERY_GRACE,
    )
    return _funding_frame_to_map(history)


def _funding_frame_to_map(frame: pd.DataFrame) -> dict[pd.Timestamp, float]:
    required = {"timestamp", "funding_rate", "source"}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        raise RuntimeError("invalid Hyperliquid funding-history response")
    if not frame.empty and not frame["source"].eq("hl_funding_history").all():
        raise RuntimeError("funding history is not Hyperliquid-sourced")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    return {
        pd.Timestamp(timestamp): float(rate)
        for timestamp, rate in zip(timestamps, frame["funding_rate"], strict=True)
    }


def _utc_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")
