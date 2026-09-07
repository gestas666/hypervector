"""Descriptive trade cadence and net payoff statistics without promotion authority."""

from __future__ import annotations

import numpy as np
import pandas as pd

_COLUMNS = ("entry_time_utc", "exit_time_utc", "net_pnl_usd")
_SECONDS_PER_HOUR = 3600.0
_SECONDS_PER_DAY = 86400.0


def summarize_trade_activity(
    trades: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, object]:
    """Describe all completed modeled trades within explicit observation bounds."""
    frame = _validated_trades(trades, start, end)
    pnl = frame.net_pnl_usd
    positive, negative = pnl.loc[pnl.gt(0)], pnl.loc[pnl.lt(0)]
    days = (end - start).total_seconds() / _SECONDS_PER_DAY
    active_days = frame.entry_time_utc.dt.floor("D").nunique()
    gaps = frame.entry_time_utc.sort_values().diff().dt.total_seconds().dropna()
    hours = (frame.exit_time_utc - frame.entry_time_utc).dt.total_seconds()
    return {
        "completed_trades": len(frame),
        "calendar_days": days,
        "entry_active_days": int(active_days),
        "trades_per_calendar_day": len(frame) / days,
        "trades_per_entry_active_day": len(frame) / active_days
        if active_days
        else None,
        "wins": len(positive),
        "losses": len(negative),
        "breakeven": int(pnl.eq(0).sum()),
        "net_win_rate_pct": len(positive) / len(frame) * 100 if len(frame) else None,
        "net_usd": float(pnl.sum()),
        "mean_net_usd": _statistic(pnl, "mean"),
        "mean_win_usd": _statistic(positive, "mean"),
        "median_win_usd": _statistic(positive, "median"),
        "mean_loss_usd": _statistic(negative, "mean"),
        "median_loss_usd": _statistic(negative, "median"),
        "net_excluding_largest_usd": float(pnl.sum() - positive.nlargest(1).sum()),
        "net_excluding_top_three_winners_usd": float(
            pnl.sum() - positive.nlargest(3).sum()
        ),
        "mean_hold_hours": _statistic(hours / _SECONDS_PER_HOUR, "mean"),
        "maximum_entry_gap_hours": _statistic(gaps / _SECONDS_PER_HOUR, "max"),
        "median_entry_gap_hours": _statistic(gaps / _SECONDS_PER_HOUR, "median"),
        "execution_authority": "none",
    }


def _validated_trades(
    trades: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    if start.tz is None or end.tz is None or not start < end:
        raise ValueError("activity observation bounds must be aware and increasing")
    missing = set(_COLUMNS).difference(trades.columns)
    if missing:
        raise ValueError(f"activity trades missing columns: {sorted(missing)}")
    frame = trades.loc[:, list(_COLUMNS)].copy()
    for column in _COLUMNS[:2]:
        values = [pd.Timestamp(value) for value in frame[column]]
        if any(pd.isna(value) or value.tz is None for value in values):
            raise ValueError("activity trade timestamps must be timezone-aware")
        frame[column] = pd.to_datetime(values, utc=True)
    frame["net_pnl_usd"] = pd.to_numeric(frame.net_pnl_usd, errors="raise")
    if not np.isfinite(frame.net_pnl_usd.to_numpy(dtype=float)).all():
        raise ValueError("activity net PnL must be finite")
    invalid = (
        frame.entry_time_utc.lt(start)
        | frame.entry_time_utc.ge(end)
        | frame.exit_time_utc.lt(frame.entry_time_utc)
        | frame.exit_time_utc.gt(end)
    )
    if invalid.any():
        raise ValueError("activity trade timestamps violate observation bounds")
    return frame


def _statistic(values: pd.Series, operation: str) -> float | None:
    if values.empty:
        return None
    return float(values.agg(operation))
