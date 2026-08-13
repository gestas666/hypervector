"""Close-only diagnostic replay for the pinned Hypertrader BTC B/C recipe."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

_BAR = pd.Timedelta(minutes=5)
_FEE_BPS = 8.0
_TP_BPS = 20.0
_TP_POINTS = 130.0
_EVENT_COLUMNS = {
    "recipe_id",
    "label_time_utc",
    "decision_time_utc",
    "side",
    "maximum_hold_seconds",
}


def _validate(events: pd.DataFrame, bars: pd.DataFrame) -> None:
    missing = _EVENT_COLUMNS.difference(events.columns)
    if missing:
        raise ValueError(f"Hypertrader recipe events missing: {sorted(missing)}")
    if "close" not in bars.columns:
        raise ValueError("Hypertrader close replay bars missing: ['close']")
    for frame, label in ((events, "events"), (bars, "bars")):
        index = frame.index
        if label == "events":
            continue
        if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
            raise ValueError(f"Hypertrader close replay {label} require UTC timestamps")
        if not index.is_monotonic_increasing or not index.is_unique:
            raise ValueError(
                f"Hypertrader close replay {label} must be ordered and unique"
            )
    if not events["side"].isin(("long", "short")).all():
        raise ValueError("Hypertrader close replay side must be long or short")


def _target_hit(entry: float, price: float, side: str) -> bool:
    sign = 1.0 if side == "long" else -1.0
    gross_bps = sign * (price / entry - 1.0) * 10_000.0
    points = sign * (price - entry)
    return gross_bps >= _TP_BPS or points >= _TP_POINTS


def _trade_row(event: Mapping[str, object], bars: pd.DataFrame) -> dict[str, object]:
    label_time = pd.Timestamp(event["label_time_utc"])
    entry = float(bars.at[label_time, "close"])
    side = str(event["side"])
    maximum = float(event["maximum_hold_seconds"])
    hold_bars = int(maximum / _BAR.total_seconds())
    future = bars.loc[label_time + _BAR : label_time + hold_bars * _BAR, "close"]
    hits = future.loc[future.map(lambda price: _target_hit(entry, float(price), side))]
    if not hits.empty:
        exit_time = pd.Timestamp(hits.index[0])
        exit_price = float(hits.iloc[0])
        reason = "tp"
    elif len(future) == hold_bars:
        exit_time = pd.Timestamp(future.index[-1])
        exit_price = float(future.iloc[-1])
        reason = "timeout"
    else:
        exit_time = None
        exit_price = None
        reason = "unresolved"
    sign = 1.0 if side == "long" else -1.0
    gross = None if exit_price is None else sign * (exit_price / entry - 1.0) * 10_000.0
    return {
        **dict(event),
        "admission": "accepted",
        "entry_price": entry,
        "exit_time_utc": exit_time,
        "exit_price": exit_price,
        "exit_reason": reason,
        "gross_bps": None if gross is None else round(gross, 6),
        "net_bps": None if gross is None else round(gross - _FEE_BPS, 6),
    }


def _overlap_row(event: Mapping[str, object]) -> dict[str, object]:
    return {
        **dict(event),
        "admission": "overlap_skipped",
        "entry_price": None,
        "exit_time_utc": None,
        "exit_price": None,
        "exit_reason": None,
        "gross_bps": None,
        "net_bps": None,
    }


def evaluate_close_recipe(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    serialized: bool,
) -> pd.DataFrame:
    """Replay source close targets independently or with one-position serialization."""
    _validate(events, bars)
    ordered = events.sort_values("decision_time_utc", kind="stable")
    rows: list[dict[str, object]] = []
    active_until: pd.Timestamp | None = None
    for event in ordered.to_dict(orient="records"):
        decision_time = pd.Timestamp(event["decision_time_utc"])
        if serialized and active_until is not None and decision_time < active_until:
            rows.append(_overlap_row(event))
            continue
        trade = _trade_row(event, bars)
        rows.append(trade)
        exit_time = trade["exit_time_utc"]
        if exit_time is None:
            active_until = decision_time + pd.Timedelta(
                seconds=float(event["maximum_hold_seconds"])
            )
        else:
            active_until = pd.Timestamp(exit_time) + _BAR
    return pd.DataFrame(rows)


def summarize_close_recipe(trades: pd.DataFrame) -> dict[str, int | float | None]:
    """Summarize accepted close replay outcomes without hiding skipped events."""
    accepted = trades.loc[trades["admission"].eq("accepted")]
    closed = accepted.loc[accepted["exit_reason"].isin(("tp", "timeout"))]
    net = pd.to_numeric(closed["net_bps"], errors="raise")
    return {
        "events": len(trades),
        "accepted": len(accepted),
        "overlap_skipped": int(trades["admission"].eq("overlap_skipped").sum()),
        "closed": len(closed),
        "tp": int(closed["exit_reason"].eq("tp").sum()),
        "timeout": int(closed["exit_reason"].eq("timeout").sum()),
        "win_rate": None if closed.empty else round(float(net.gt(0).mean()), 6),
        "mean_net_bps": None if closed.empty else round(float(net.mean()), 6),
        "sum_net_bps": round(float(net.sum()), 6),
    }
