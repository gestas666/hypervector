"""Causal minute paths from verified exchange-mark observations."""

from __future__ import annotations

import pandas as pd

from hypervector.research.cohort_profit_lock_l2_proxy import ProxyMinuteBar

_MINUTE_MS = 60_000


def exact_mark_minute_bars(frame: pd.DataFrame) -> dict[int, ProxyMinuteBar]:
    """Aggregate sampled exchange marks into minute OHLC and continuity evidence."""
    required = {"ts_ms", "mark_price"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"exact mark evidence missing columns: {missing}")
    selected = frame.loc[:, ["ts_ms", "mark_price"]].copy()
    selected["ts_ms"] = pd.to_numeric(selected["ts_ms"], errors="raise").astype("int64")
    selected["mark_price"] = pd.to_numeric(
        selected["mark_price"], errors="raise"
    ).astype("float64")
    if selected.empty or selected["ts_ms"].lt(0).any():
        raise ValueError("exact mark evidence requires nonnegative timestamp rows")
    if selected["mark_price"].le(0.0).any():
        raise ValueError("exact mark prices must be positive")
    selected = selected.sort_values("ts_ms", kind="stable")
    if selected["ts_ms"].duplicated().any():
        raise ValueError("exact mark timestamps must be unique")
    selected["bar_ms"] = selected["ts_ms"] // _MINUTE_MS * _MINUTE_MS
    return {
        int(bar_ms): _minute_bar(int(bar_ms), group)
        for bar_ms, group in selected.groupby("bar_ms", sort=True)
    }


def _minute_bar(bar_ms: int, frame: pd.DataFrame) -> ProxyMinuteBar:
    times = frame["ts_ms"]
    prices = frame["mark_price"]
    internal_gap = times.diff().dropna().max()
    return ProxyMinuteBar(
        timestamp_ms=bar_ms,
        open=float(prices.iloc[0]),
        high=float(prices.max()),
        low=float(prices.min()),
        close=float(prices.iloc[-1]),
        snapshot_count=len(frame),
        first_delay_ms=int(times.iloc[0]) - bar_ms,
        maximum_internal_gap_ms=(0 if pd.isna(internal_gap) else int(internal_gap)),
        end_boundary_age_ms=bar_ms + _MINUTE_MS - int(times.iloc[-1]),
    )
