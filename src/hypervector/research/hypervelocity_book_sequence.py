"""Causal multi-horizon order-book sequence features for research models."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.hypervelocity_attribution import (
    prepare_book_pressure,
    window_ofi,
)

SEQUENCE_BOOK_RAW_COLUMNS: tuple[str, ...] = (
    "book_sequence_snapshots_15s",
    "obi_5_mean_15s",
    "obi_5_delta_15s",
    "ofi_top_15s_normalized",
    "book_sequence_snapshots_60s",
    "obi_5_mean_60s",
    "obi_5_delta_60s",
    "obi_5_sign_mean_60s",
    "ofi_top_60s_normalized",
    "micro_price_delta_bps_mean_60s",
    "spread_bps_median_60s",
)


def _missing_row() -> dict[str, float | int]:
    return {
        name: 0 if name.startswith("book_sequence_snapshots") else float("nan")
        for name in SEQUENCE_BOOK_RAW_COLUMNS
    }


def _delta(values: pd.Series) -> float:
    if len(values) < 2:
        return float("nan")
    return float(values.iloc[-1] - values.iloc[0])


def _window(
    frame: pd.DataFrame,
    timestamps: np.ndarray,
    end: int,
    start_ms: int,
) -> pd.DataFrame:
    first = int(np.searchsorted(timestamps, start_ms, side="left"))
    return frame.iloc[first : end + 1]


def _sequence_row(
    frame: pd.DataFrame,
    timestamps: np.ndarray,
    target_ms: int,
    max_age_ms: int,
) -> dict[str, float | int]:
    end = int(np.searchsorted(timestamps, target_ms, side="right")) - 1
    if end < 0 or target_ms - int(timestamps[end]) > max_age_ms:
        return _missing_row()
    short = _window(frame, timestamps, end, target_ms - 15_000)
    long = _window(frame, timestamps, end, target_ms - 60_000)
    short_obi = short["obi_5"].astype(float)
    long_obi = long["obi_5"].astype(float)
    return {
        "book_sequence_snapshots_15s": len(short),
        "obi_5_mean_15s": float(short_obi.mean()),
        "obi_5_delta_15s": _delta(short_obi),
        "ofi_top_15s_normalized": window_ofi(short)[1],
        "book_sequence_snapshots_60s": len(long),
        "obi_5_mean_60s": float(long_obi.mean()),
        "obi_5_delta_60s": _delta(long_obi),
        "obi_5_sign_mean_60s": float(np.sign(long_obi).mean()),
        "ofi_top_60s_normalized": window_ofi(long)[1],
        "micro_price_delta_bps_mean_60s": float(
            long["micro_price_delta_bps"].astype(float).mean()
        ),
        "spread_bps_median_60s": float(long["spread_bps"].astype(float).median()),
    }


def align_book_sequence(
    signal_times: pd.DatetimeIndex,
    books: pd.DataFrame,
    *,
    max_age_ms: int = 6_000,
) -> pd.DataFrame:
    """Align strictly backward 15s/60s L2 sequences to signal timestamps."""
    if max_age_ms < 0:
        raise ValueError("book sequence age must be non-negative")
    if signal_times.tz is None:
        raise ValueError("book sequence signals must be timezone-aware")
    frame = prepare_book_pressure(books)
    timestamps = frame["ts_ms"].to_numpy(dtype=np.int64)
    targets = signal_times.as_unit("ms").asi8
    rows = [
        _sequence_row(frame, timestamps, int(target), max_age_ms) for target in targets
    ]
    return pd.DataFrame(rows, index=signal_times, columns=SEQUENCE_BOOK_RAW_COLUMNS)
