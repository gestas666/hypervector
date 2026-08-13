"""Approximate tracker-only source exits using timestamped venue marks."""

from __future__ import annotations

import math
from typing import Literal

import pandas as pd

_LOGICAL_COLUMNS = {
    "open_ts",
    "close_ts",
    "side",
    "entry_price",
    "timestamp_provenance",
}
_PRICE_COLUMNS = {"timestamp", "mark_price"}


def _validated_positions(logical: pd.DataFrame) -> pd.DataFrame:
    missing = _LOGICAL_COLUMNS.difference(logical.columns)
    if missing:
        raise ValueError(f"source exit positions missing: {sorted(missing)}")
    frame = logical.loc[
        logical["timestamp_provenance"].eq("tracker_only") & logical["close_ts"].notna()
    ].copy()
    if frame.empty:
        raise ValueError("source exit proxy requires closed tracker-only positions")
    frame["open_ts"] = pd.to_datetime(frame["open_ts"], utc=True, format="ISO8601")
    frame["close_ts"] = pd.to_datetime(frame["close_ts"], utc=True, format="ISO8601")
    frame["entry_price"] = pd.to_numeric(frame["entry_price"], errors="raise")
    if not frame["side"].isin(("long", "short")).all():
        raise ValueError("source exit proxy sides must be long or short")
    if (frame["entry_price"] <= 0.0).any():
        raise ValueError("source exit proxy entry prices must be positive")
    return frame.sort_values("close_ts", kind="stable").reset_index(drop=True)


def _validated_prices(prices: pd.DataFrame) -> pd.DataFrame:
    missing = _PRICE_COLUMNS.difference(prices.columns)
    if missing:
        raise ValueError(f"source exit mark evidence missing: {sorted(missing)}")
    frame = pd.DataFrame(
        {
            "mark_ts": pd.to_datetime(prices["timestamp"], utc=True, format="ISO8601"),
            "mark_price": pd.to_numeric(prices["mark_price"], errors="raise"),
        }
    ).sort_values("mark_ts", kind="stable")
    if frame.empty or frame["mark_ts"].duplicated().any():
        raise ValueError("source exit marks must be non-empty and timestamp-unique")
    if (frame["mark_price"] <= 0.0).any():
        raise ValueError("source exit marks must be positive")
    return frame.reset_index(drop=True)


def _aligned_marks(
    positions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    direction: Literal["backward", "nearest"],
    tolerance: pd.Timedelta,
) -> pd.DataFrame:
    return pd.merge_asof(
        positions,
        prices,
        left_on="close_ts",
        right_on="mark_ts",
        direction=direction,
        tolerance=tolerance,
    )


def _margin_pct(
    side: pd.Series,
    entry_price: pd.Series,
    mark_price: pd.Series,
    leverage: float,
) -> pd.Series:
    sign = side.map({"long": 1.0, "short": -1.0})
    return 100.0 * leverage * sign * (mark_price - entry_price) / entry_price


def build_tracker_exit_proxies(
    logical: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    leverage: float = 40.0,
    tolerance_seconds: float = 120.0,
) -> pd.DataFrame:
    """Join closed tracker observations to backward and nearest venue marks."""
    if not math.isfinite(leverage) or leverage <= 0.0:
        raise ValueError("source exit proxy leverage must be finite and positive")
    if not math.isfinite(tolerance_seconds) or tolerance_seconds <= 0.0:
        raise ValueError("source exit proxy tolerance must be finite and positive")
    positions = _validated_positions(logical)
    marks = _validated_prices(prices)
    tolerance = pd.Timedelta(seconds=tolerance_seconds)
    backward = _aligned_marks(
        positions, marks, direction="backward", tolerance=tolerance
    )
    nearest = _aligned_marks(positions, marks, direction="nearest", tolerance=tolerance)
    if backward["mark_price"].isna().any() or nearest["mark_price"].isna().any():
        raise ValueError("source exit proxy has no mark inside the tolerance")
    output = positions.copy()
    output["backward_mark_ts"] = backward["mark_ts"]
    output["backward_mark_price"] = backward["mark_price"]
    output["backward_mark_age_seconds"] = (
        output["close_ts"] - output["backward_mark_ts"]
    ).dt.total_seconds()
    output["nearest_mark_ts"] = nearest["mark_ts"]
    output["nearest_mark_price"] = nearest["mark_price"]
    output["nearest_mark_offset_seconds"] = (
        output["nearest_mark_ts"] - output["close_ts"]
    ).dt.total_seconds()
    output["backward_gross_margin_pct"] = _margin_pct(
        output["side"], output["entry_price"], output["backward_mark_price"], leverage
    )
    output["nearest_gross_margin_pct"] = _margin_pct(
        output["side"], output["entry_price"], output["nearest_mark_price"], leverage
    )
    return output


def summarize_tracker_exit_proxies(proxies: pd.DataFrame) -> dict[str, object]:
    """Return bounded descriptive counts without treating marks as fills."""
    required = {"backward_gross_margin_pct", "nearest_gross_margin_pct"}
    missing = required.difference(proxies.columns)
    if missing:
        raise ValueError(f"source exit proxy summary missing: {sorted(missing)}")
    backward = proxies["backward_gross_margin_pct"].astype(float)
    nearest = proxies["nearest_gross_margin_pct"].astype(float)
    return {
        "positions": len(proxies),
        "backward_positive": int(backward.gt(0.0).sum()),
        "backward_negative": int(backward.lt(0.0).sum()),
        "backward_median_margin_pct": float(backward.median()),
        "backward_minimum_margin_pct": float(backward.min()),
        "backward_maximum_margin_pct": float(backward.max()),
        "nearest_positive": int(nearest.gt(0.0).sum()),
        "nearest_negative": int(nearest.lt(0.0).sum()),
        "nearest_median_margin_pct": float(nearest.median()),
        "nearest_minimum_margin_pct": float(nearest.min()),
        "nearest_maximum_margin_pct": float(nearest.max()),
    }
