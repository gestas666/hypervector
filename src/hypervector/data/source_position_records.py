"""Reconcile duplicate records emitted by the external position trackers."""

from __future__ import annotations

import math

import pandas as pd

_REQUIRED_COLUMNS = {
    "record_source",
    "symbol",
    "side",
    "open_time_utc",
    "close_time_utc",
    "entry_price",
    "quantity",
}
_DUPLICATE_SOURCES = frozenset({"position_peak_only", "trade_only"})
_CLOSE_TOLERANCE = pd.Timedelta(seconds=60)


def _normalized_view(records: pd.DataFrame) -> pd.DataFrame:
    view = records.loc[:, sorted(_REQUIRED_COLUMNS)].copy()
    view["record_source"] = view["record_source"].astype(str)
    view["symbol"] = view["symbol"].astype(str).str.upper()
    view["side"] = view["side"].astype(str).str.lower()
    view["open_time_utc"] = pd.to_datetime(
        view["open_time_utc"], utc=True, format="ISO8601"
    )
    view["close_time_utc"] = pd.to_datetime(
        view["close_time_utc"], utc=True, errors="coerce", format="ISO8601"
    )
    view["entry_price"] = pd.to_numeric(view["entry_price"], errors="coerce")
    view["quantity"] = pd.to_numeric(view["quantity"], errors="coerce")
    if view["open_time_utc"].isna().any():
        raise ValueError("source position reconciliation found an invalid open time")
    return view


def _same_number(left: object, right: object) -> bool:
    if pd.isna(left) or pd.isna(right):
        return False
    return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-12)


def _is_duplicate_pair(left: pd.Series, right: pd.Series) -> bool:
    sources = frozenset({str(left["record_source"]), str(right["record_source"])})
    if sources != _DUPLICATE_SOURCES:
        return False
    if left["symbol"] != right["symbol"] or left["side"] != right["side"]:
        return False
    if not _same_number(left["entry_price"], right["entry_price"]):
        return False
    if not _same_number(left["quantity"], right["quantity"]):
        return False
    if pd.isna(left["close_time_utc"]) or pd.isna(right["close_time_utc"]):
        return False
    close_delta = abs(left["close_time_utc"] - right["close_time_utc"])
    overlaps = (
        left["open_time_utc"] <= right["close_time_utc"]
        and right["open_time_utc"] <= left["close_time_utc"]
    )
    return bool(overlaps and close_delta <= _CLOSE_TOLERANCE)


def reconcile_source_position_records(records: pd.DataFrame) -> pd.DataFrame:
    """Drop a peak-only row when a matching trade-only record supersedes it."""
    if "record_source" not in records:
        return records.copy()
    missing = _REQUIRED_COLUMNS.difference(records.columns)
    if missing:
        raise ValueError(
            f"source position reconciliation missing columns: {sorted(missing)}"
        )
    view = _normalized_view(records)
    peaks = view.index[view["record_source"].eq("position_peak_only")]
    trades = view.index[view["record_source"].eq("trade_only")]
    superseded: set[object] = set()
    for peak_index in peaks:
        peak = view.loc[peak_index]
        if any(_is_duplicate_pair(peak, view.loc[index]) for index in trades):
            superseded.add(peak_index)
    return records.drop(index=list(superseded)).reset_index(drop=True)
