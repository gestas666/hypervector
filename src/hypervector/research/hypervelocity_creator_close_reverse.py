"""Reconstruct creator close minutes without fabricating exact exit fills."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.research.hypervelocity_reentry_compare import (
    logical_source_positions,
)

_BAR_COLUMNS = {"timestamp", "open", "high", "low", "close", "source"}
_POSITION_COLUMNS = {
    "open_time_utc",
    "close_time_utc",
    "side",
    "status",
    "entry_price",
    "exit_reason",
}


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = _BAR_COLUMNS.difference(bars.columns)
    if missing:
        raise ValueError(f"creator close bars missing columns: {sorted(missing)}")
    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if frame["timestamp"].duplicated().any():
        raise ValueError("creator close bars require unique timestamps")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("creator close bars require chronological timestamps")
    numeric = sorted(_BAR_COLUMNS.difference({"timestamp", "source"}))
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    return frame.set_index("timestamp")


def _validated_positions(positions: pd.DataFrame) -> pd.DataFrame:
    missing = _POSITION_COLUMNS.difference(positions.columns)
    if missing:
        raise ValueError(f"creator positions missing columns: {sorted(missing)}")
    frame = positions.copy()
    frame["open_ts"] = pd.to_datetime(frame["open_time_utc"], utc=True)
    frame["close_ts"] = pd.to_datetime(
        frame["close_time_utc"], utc=True, errors="coerce"
    )
    frame["entry_price"] = pd.to_numeric(frame["entry_price"], errors="raise")
    selected = frame["exit_reason"].astype(str).eq("closed_no_trade_row")
    selected &= frame["status"].astype(str).eq("closed")
    missing_exit = frame.loc[selected].sort_values("open_ts").copy()
    if missing_exit.empty:
        raise ValueError("creator positions contain no closed_no_trade_row evidence")
    if missing_exit["close_ts"].isna().any():
        raise ValueError("creator missing-exit rows require close timestamps")
    if not missing_exit["side"].isin(("long", "short")).all():
        raise ValueError("creator position sides must be long|short")
    return missing_exit


def _margin_returns(
    row: pd.Series,
    bar: pd.Series,
    leverage: float,
) -> dict[str, float]:
    sign = 1.0 if row["side"] == "long" else -1.0
    entry = float(row["entry_price"])
    values = {
        name: sign * (float(bar[name]) / entry - 1.0) * leverage * 100.0
        for name in ("open", "high", "low", "close")
    }
    return {
        "close": values["close"],
        "low": min(values.values()),
        "high": max(values.values()),
    }


def _next_position(
    logical: pd.DataFrame,
    close_ts: pd.Timestamp,
    side: str,
) -> dict[str, object]:
    later = logical.loc[logical["open_ts"] > close_ts]
    if later.empty:
        return {
            "next_position_side": None,
            "next_position_open_utc": None,
            "next_position_open_latency_seconds": None,
            "next_position_is_opposite": None,
        }
    next_row = later.iloc[0]
    latency = (next_row["open_ts"] - close_ts).total_seconds()
    return {
        "next_position_side": str(next_row["side"]),
        "next_position_open_utc": next_row["open_ts"].isoformat(),
        "next_position_open_latency_seconds": float(latency),
        "next_position_is_opposite": bool(next_row["side"] != side),
    }


def _position_id(row: pd.Series) -> int | None:
    value = row.get("position_peak_id")
    return None if value is None or pd.isna(value) else int(value)


def _position_evidence(
    row: pd.Series,
    bar: pd.Series,
    logical: pd.DataFrame,
    leverage: float,
) -> dict[str, object]:
    close_ts = pd.Timestamp(row["close_ts"])
    returns = _margin_returns(row, bar, leverage)
    outcome = "favorable" if returns["close"] > 0.0 else "adverse"
    if math.isclose(returns["close"], 0.0, abs_tol=1e-12):
        outcome = "flat"
    return {
        "position_peak_id": _position_id(row),
        "side": str(row["side"]),
        "open_time_utc": pd.Timestamp(row["open_ts"]).isoformat(),
        "close_time_utc": close_ts.isoformat(),
        "close_minute_utc": close_ts.floor("min").isoformat(),
        "bar_source": str(bar["source"]),
        "entry_price": float(row["entry_price"]),
        "close_minute_ohlc": {
            name: float(bar[name]) for name in ("open", "high", "low", "close")
        },
        "estimated_close_margin_pct": returns["close"],
        "estimated_minute_margin_low_pct": returns["low"],
        "estimated_minute_margin_high_pct": returns["high"],
        "estimated_outcome": outcome,
        **_next_position(logical, close_ts, str(row["side"])),
    }


def creator_close_reverse_evidence(
    positions: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    leverage: float = 40.0,
) -> dict[str, object]:
    """Return side-aware close-minute estimates and next-position timing."""
    if not math.isfinite(leverage) or leverage <= 0.0:
        raise ValueError("creator reconstruction leverage must be positive")
    close_rows = _validated_positions(positions)
    venue_bars = _validated_bars(bars)
    logical = logical_source_positions(positions).sort_values("open_ts")
    evidence: list[dict[str, object]] = []
    for _, row in close_rows.iterrows():
        minute = pd.Timestamp(row["close_ts"]).floor("min")
        if minute not in venue_bars.index:
            raise ValueError(
                f"missing exact Hyperliquid close minute: {minute.isoformat()}"
            )
        if str(venue_bars.loc[minute, "source"]) != "hl":
            raise ValueError(
                f"creator close minute is not exact Hyperliquid source: "
                f"{minute.isoformat()}"
            )
        evidence.append(
            _position_evidence(row, venue_bars.loc[minute], logical, leverage)
        )
    counts = {
        label: sum(item["estimated_outcome"] == label for item in evidence)
        for label in ("adverse", "favorable", "flat")
    }
    adverse = [item for item in evidence if item["estimated_outcome"] == "adverse"]
    reversals = [
        item
        for item in adverse
        if item["next_position_is_opposite"] is True
        and float(item["next_position_open_latency_seconds"]) <= 180.0
    ]
    return {
        "raw_missing_exit_rows": len(evidence),
        "estimated_outcomes": counts,
        "adverse_followed_by_opposite_within_180_seconds": len(reversals),
        "all_adverse_followed_by_opposite_within_180_seconds": (
            bool(adverse) and len(reversals) == len(adverse)
        ),
        "positions": evidence,
    }
