"""Point-in-time Hypervelocity regime and orderbook attribution.

This module is research-only. Its outputs annotate replay lifecycles and do not
authorize, reject, size, route, or exit strategy orders.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
import pandas as pd

_BOOK_COLUMNS = (
    "book_snapshot_ts_ms",
    "book_snapshot_age_ms",
    "obi_5",
    "obi_20",
    "spread_bps",
    "micro_price_delta_bps",
    "obi_5_trailing_median",
    "obi_20_trailing_median",
    "ofi_top_5s",
    "ofi_top_5s_normalized",
    "book_window_snapshots",
)

_TOP_OF_BOOK_COLUMNS = (
    "best_bid",
    "best_ask",
    "best_bid_size",
    "best_ask_size",
)


def regime_age_bars(states: pd.Series) -> pd.Series:
    """Return zero-based bars elapsed in each contiguous regime episode."""
    if states.empty:
        return pd.Series(dtype="int64", index=states.index)
    episode = states.ne(states.shift()).cumsum()
    return states.groupby(episode, sort=False).cumcount().astype("int64")


def compression_age_bars(bbwp: pd.Series, *, threshold: float) -> pd.Series:
    """Return causal bars since the latest observed BBWP compression."""
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
        raise ValueError("BBWP compression threshold must be within [0, 100]")
    age: int | None = None
    values: list[float] = []
    for value in bbwp:
        if pd.isna(value):
            if age is not None:
                age += 1
            values.append(float("nan"))
            continue
        if float(value) < threshold:
            age = 0
        elif age is not None:
            age += 1
        values.append(float(age) if age is not None else float("nan"))
    return pd.Series(values, index=bbwp.index, dtype="float64")


def _validate_bar_inputs(bars: pd.DataFrame, decisions: pd.DataFrame) -> None:
    required_bars = {"open", "high", "low", "close", "volume"}
    required_decisions = {"state_5m", "context_15m", "bbwp_percentile"}
    missing_bars = required_bars.difference(bars.columns)
    missing_decisions = required_decisions.difference(decisions.columns)
    if missing_bars:
        raise ValueError(f"attribution bars missing columns: {sorted(missing_bars)}")
    if missing_decisions:
        raise ValueError(
            f"attribution decisions missing columns: {sorted(missing_decisions)}"
        )
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("attribution bars require a DatetimeIndex")
    if not bars.index.equals(decisions.index):
        raise ValueError("attribution bars and decisions require the same index")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("attribution bar index must be unique and increasing")


def _completed_five_minute_bars(bars: pd.DataFrame) -> pd.DataFrame:
    grouped = bars.resample("5min", label="left", closed="left")
    frame = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    complete = grouped["close"].count().eq(5)
    frame = frame.loc[complete].dropna()
    frame.index = frame.index + pd.Timedelta(minutes=4)
    return frame


def _prior_structure(bars: pd.DataFrame, *, lookback: int) -> pd.DataFrame:
    if lookback < 1:
        raise ValueError("5m structure lookback must be positive")
    five = _completed_five_minute_bars(bars)
    levels = pd.DataFrame(
        {
            "prior_5m_resistance": five["high"].shift(1).rolling(lookback).max(),
            "prior_5m_support": five["low"].shift(1).rolling(lookback).min(),
        },
        index=five.index,
    )
    return levels.reindex(bars.index, method="ffill")


def _structure_distances(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    structure: pd.DataFrame,
) -> pd.DataFrame:
    close = bars["close"].astype(float)
    support = 10_000.0 * (close - structure["prior_5m_support"]).abs() / close
    resistance = 10_000.0 * (close - structure["prior_5m_resistance"]).abs() / close
    nearest = pd.concat([support, resistance], axis=1).min(axis=1)
    directional = nearest.copy()
    directional = directional.mask(decisions["state_5m"].eq("TREND_UP"), support)
    directional = directional.mask(decisions["state_5m"].eq("TREND_DOWN"), resistance)
    return pd.DataFrame(
        {
            "support_distance_bps": support,
            "resistance_distance_bps": resistance,
            "nearest_structure_distance_bps": nearest,
            "directional_structure_distance_bps": directional,
        },
        index=bars.index,
    )


def build_bar_annotations(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    structure_lookback: int = 240,
    compression_threshold: float = 25.0,
) -> pd.DataFrame:
    """Build causal regime, BBWP, context, and true price-level annotations."""
    _validate_bar_inputs(bars, decisions)
    structure = _prior_structure(bars, lookback=structure_lookback)
    distances = _structure_distances(bars, decisions, structure)
    return pd.concat(
        [
            decisions[["state_5m", "context_15m", "bbwp_percentile"]],
            pd.DataFrame(
                {
                    "regime_age_bars": regime_age_bars(decisions["state_5m"]),
                    "bbwp_compression_age_bars": compression_age_bars(
                        decisions["bbwp_percentile"], threshold=compression_threshold
                    ),
                },
                index=bars.index,
            ),
            structure,
            distances,
        ],
        axis=1,
    )


def _missing_book_row() -> dict[str, float | int]:
    return {
        "book_snapshot_ts_ms": float("nan"),
        "book_snapshot_age_ms": float("nan"),
        "obi_5": float("nan"),
        "obi_20": float("nan"),
        "spread_bps": float("nan"),
        "micro_price_delta_bps": float("nan"),
        "obi_5_trailing_median": float("nan"),
        "obi_20_trailing_median": float("nan"),
        "ofi_top_5s": float("nan"),
        "ofi_top_5s_normalized": float("nan"),
        "book_window_snapshots": 0,
    }


def prepare_book_pressure(books: pd.DataFrame) -> pd.DataFrame:
    """Validate and causally enrich raw book-pressure observations."""
    required = {"ts_ms", "obi_5", "obi_20", "spread_bps", "micro_price_delta_bps"}
    missing = required.difference(books.columns)
    if missing:
        raise ValueError(f"book pressure evidence missing columns: {sorted(missing)}")
    available_top = set(_TOP_OF_BOOK_COLUMNS).intersection(books.columns)
    if available_top and available_top != set(_TOP_OF_BOOK_COLUMNS):
        missing_top = set(_TOP_OF_BOOK_COLUMNS).difference(books.columns)
        raise ValueError(
            f"book pressure evidence has partial top-of-book fields: {sorted(missing_top)}"
        )
    selected = sorted(required.union(available_top))
    frame = books.loc[:, selected].copy()
    frame["ts_ms"] = pd.to_numeric(frame["ts_ms"], errors="raise").astype("int64")
    frame = frame.sort_values("ts_ms", kind="stable").reset_index(drop=True)
    if frame["ts_ms"].duplicated().any():
        raise ValueError("book pressure evidence has duplicate timestamps")
    return _add_top_of_book_ofi(frame)


def _add_top_of_book_ofi(frame: pd.DataFrame) -> pd.DataFrame:
    """Add causal Cont-style top-of-book queue-change events when available."""
    output = frame.copy()
    if not set(_TOP_OF_BOOK_COLUMNS).issubset(output.columns):
        output["ofi_top_event"] = float("nan")
        return output
    top = output.loc[:, _TOP_OF_BOOK_COLUMNS].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(top.to_numpy(dtype=float)).all():
        raise ValueError("top-of-book OFI fields must be finite")
    if (top[["best_bid", "best_ask"]] <= 0.0).any().any():
        raise ValueError("top-of-book OFI prices must be positive")
    if (top[["best_bid_size", "best_ask_size"]] < 0.0).any().any():
        raise ValueError("top-of-book OFI sizes must be non-negative")
    prior = top.shift(1)
    bid_event = top["best_bid_size"].where(
        top["best_bid"].ge(prior["best_bid"]), 0.0
    ) - prior["best_bid_size"].where(top["best_bid"].le(prior["best_bid"]), 0.0)
    ask_event = -top["best_ask_size"].where(
        top["best_ask"].le(prior["best_ask"]), 0.0
    ) + prior["best_ask_size"].where(top["best_ask"].ge(prior["best_ask"]), 0.0)
    output["ofi_top_event"] = (bid_event + ask_event).where(prior.notna().all(axis=1))
    return output


def window_ofi(window: pd.DataFrame) -> tuple[float, float]:
    """Return raw and displayed-depth-normalized OFI for one causal window."""
    events = window["ofi_top_event"].dropna()
    if events.empty or not set(_TOP_OF_BOOK_COLUMNS).issubset(window.columns):
        return float("nan"), float("nan")
    raw = float(events.sum())
    top_depth = window["best_bid_size"] + window["best_ask_size"]
    scale = float(top_depth.median())
    normalized = raw / scale if math.isfinite(scale) and scale > 0.0 else float("nan")
    return raw, normalized


def _book_row(
    frame: pd.DataFrame,
    timestamps: np.ndarray,
    target_ms: int,
    *,
    max_age_ms: int,
    trailing_window_ms: int,
) -> dict[str, float | int]:
    position = int(np.searchsorted(timestamps, target_ms, side="right")) - 1
    if position < 0:
        return _missing_book_row()
    snapshot_ms = int(timestamps[position])
    age_ms = target_ms - snapshot_ms
    if age_ms > max_age_ms:
        return _missing_book_row()
    start = int(
        np.searchsorted(timestamps, target_ms - trailing_window_ms, side="left")
    )
    window = frame.iloc[start : position + 1]
    latest = frame.iloc[position]
    ofi_raw, ofi_normalized = window_ofi(window)
    return {
        "book_snapshot_ts_ms": snapshot_ms,
        "book_snapshot_age_ms": age_ms,
        "obi_5": float(latest["obi_5"]),
        "obi_20": float(latest["obi_20"]),
        "spread_bps": float(latest["spread_bps"]),
        "micro_price_delta_bps": float(latest["micro_price_delta_bps"]),
        "obi_5_trailing_median": float(window["obi_5"].median()),
        "obi_20_trailing_median": float(window["obi_20"].median()),
        "ofi_top_5s": ofi_raw,
        "ofi_top_5s_normalized": ofi_normalized,
        "book_window_snapshots": len(window),
    }


def align_book_pressure(
    signal_times: pd.DatetimeIndex,
    books: pd.DataFrame,
    *,
    max_age_ms: int = 2_000,
    trailing_window_ms: int = 5_000,
) -> pd.DataFrame:
    """Align causal latest/trailing L2 pressure to decision timestamps."""
    if max_age_ms < 0 or trailing_window_ms < 0:
        raise ValueError("book age and trailing window must be non-negative")
    frame = prepare_book_pressure(books)
    timestamps = frame["ts_ms"].to_numpy(dtype=np.int64)
    targets = signal_times.as_unit("ms").asi8
    rows = [
        _book_row(
            frame,
            timestamps,
            int(target),
            max_age_ms=max_age_ms,
            trailing_window_ms=trailing_window_ms,
        )
        for target in targets
    ]
    return pd.DataFrame(rows, index=signal_times, columns=_BOOK_COLUMNS)


def _bucket(
    value: object, bounds: tuple[float, float], labels: tuple[str, str, str]
) -> str:
    if pd.isna(value):
        return "missing"
    numeric = float(value)
    if numeric < bounds[0]:
        return labels[0]
    if numeric < bounds[1]:
        return labels[1]
    return labels[2]


def _directional_alignment(direction: object, value: object) -> str:
    if direction not in {"long", "short"} or pd.isna(value):
        return "missing"
    pressure = float(value)
    if pressure == 0.0:
        return "neutral"
    aligned = (direction == "long" and pressure > 0.0) or (
        direction == "short" and pressure < 0.0
    )
    return "aligned" if aligned else "opposed"


def _context_alignment(direction: object, context: object) -> str:
    if direction not in {"long", "short"} or pd.isna(context):
        return "missing"
    expected = "TREND_UP" if direction == "long" else "TREND_DOWN"
    opposed = "TREND_DOWN" if direction == "long" else "TREND_UP"
    if context == expected:
        return "aligned"
    if context == opposed:
        return "opposed"
    return "non_directional"


def _joined_annotations(
    signal_times: pd.DatetimeIndex,
    bar_annotations: pd.DataFrame,
    book_annotations: pd.DataFrame,
) -> pd.DataFrame:
    available_bars = bar_annotations.copy()
    available_bars.index = available_bars.index + pd.Timedelta(minutes=1)
    bars = available_bars.reindex(signal_times).reset_index(drop=True)
    books = book_annotations.reindex(signal_times).reset_index(drop=True)
    return pd.concat([bars, books], axis=1)


def build_lifecycle_attribution(
    lifecycles: pd.DataFrame,
    bar_annotations: pd.DataFrame,
    book_annotations: pd.DataFrame,
) -> pd.DataFrame:
    """Join every replay lifecycle to annotations at its signal timestamp."""
    required = {"lifecycle_id", "direction", "signal_time_utc", "status"}
    missing = required.difference(lifecycles.columns)
    if missing:
        raise ValueError(f"replay lifecycles missing columns: {sorted(missing)}")
    output = lifecycles.reset_index(drop=True).copy()
    signal_times = pd.DatetimeIndex(pd.to_datetime(output["signal_time_utc"], utc=True))
    output = pd.concat(
        [output, _joined_annotations(signal_times, bar_annotations, book_annotations)],
        axis=1,
    )
    output["regime_age_bucket"] = output["regime_age_bars"].map(
        lambda value: _bucket(value, (5.0, 15.0), ("0-4", "5-14", "15+"))
    )
    output["structure_distance_bucket"] = output[
        "directional_structure_distance_bps"
    ].map(lambda value: _bucket(value, (25.0, 100.0), ("<25", "25-99", "100+")))
    output["bbwp_recency_bucket"] = output["bbwp_compression_age_bars"].map(
        lambda value: _bucket(value, (6.0, 31.0), ("0-5", "6-30", "31+"))
    )
    output["pressure_alignment"] = [
        _directional_alignment(direction, pressure)
        for direction, pressure in zip(
            output["direction"], output["obi_5_trailing_median"], strict=True
        )
    ]
    output["context_15m_alignment"] = [
        _context_alignment(direction, context)
        for direction, context in zip(
            output["direction"], output["context_15m"], strict=True
        )
    ]
    return output


def _count_status(values: pd.Series, status: str) -> int:
    return int(values.eq(status).sum())


def slice_outcomes(
    attributed: pd.DataFrame, dimension: str
) -> tuple[dict[str, object], ...]:
    """Report complete lifecycle and resolved-outcome counts by one dimension."""
    if dimension not in attributed:
        raise ValueError(f"attribution dimension is unavailable: {dimension}")
    buckets = attributed[dimension].fillna("missing").astype(str)
    rows: list[dict[str, object]] = []
    for bucket in sorted(buckets.unique()):
        group = attributed.loc[buckets.eq(bucket)]
        status = group["status"].astype(str)
        targets = _count_status(status, "target_completed")
        liquidations = _count_status(status, "liquidated")
        resolved = targets + liquidations
        rows.append(
            {
                "bucket": bucket,
                "lifecycles": len(group),
                "entry_fills": int(
                    group.get("entry_time_utc", pd.Series()).notna().sum()
                ),
                "resolved_trades": resolved,
                "target_completed": targets,
                "liquidated": liquidations,
                "expired": _count_status(status, "expired"),
                "canceled": _count_status(status, "canceled"),
                "open": _count_status(status, "open"),
                "pending": _count_status(status, "pending"),
                "target_rate_pct": 100.0 * targets / resolved if resolved else None,
            }
        )
    return tuple(rows)


def attribution_slices(
    attributed: pd.DataFrame,
    dimensions: Iterable[str],
) -> dict[str, tuple[dict[str, object], ...]]:
    """Return outcome slices for each requested annotation dimension."""
    return {
        dimension: slice_outcomes(attributed, dimension) for dimension in dimensions
    }
