"""Verified archive IO for Hypervelocity microstructure attribution."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_archive_audit import OxaArchiveBundle
from hypervector.data.oxa_storage import open_text_reader

_PRESSURE_COLUMNS = (
    "ts_ms",
    "obi_5",
    "obi_20",
    "spread_bps",
    "micro_price_delta_bps",
    "best_bid",
    "best_ask",
    "best_bid_size",
    "best_ask_size",
)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"native L2 {label} must be an object")
    output: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"native L2 {label} contains a non-string key")
        output[key] = item
    return output


def _finite_number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"native L2 {label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"native L2 {label} must be numeric") from exc
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "positive " if positive else "finite "
        raise ValueError(f"native L2 {label} must be {qualifier}numeric")
    return number


def _timestamp(value: object) -> int:
    number = _finite_number(value, "ts_exchange_ms", positive=True)
    if not number.is_integer():
        raise ValueError("native L2 ts_exchange_ms must be an integer")
    return int(number)


def _levels(value: object, label: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"native L2 {label} must be a non-empty array")
    levels: list[tuple[float, float]] = []
    for position, raw in enumerate(value):
        row = _mapping(raw, f"{label}[{position}]")
        price = _finite_number(row.get("px"), f"{label}[{position}].px", positive=True)
        size = _finite_number(row.get("sz"), f"{label}[{position}].sz")
        if size < 0.0:
            raise ValueError(f"native L2 {label}[{position}].sz must be non-negative")
        levels.append((price, size))
    return tuple(levels)


def _pressure(levels: tuple[tuple[float, float], ...], depth: int) -> float:
    return sum(size for _, size in levels[:depth])


def _order_pressure(bid_depth: float, ask_depth: float) -> float:
    total = bid_depth + ask_depth
    if total <= 0.0:
        return float("nan")
    return (bid_depth - ask_depth) / total


def _microprice_delta(
    best_bid: float,
    best_ask: float,
    bid_size: float,
    ask_size: float,
) -> float:
    midpoint = (best_bid + best_ask) / 2.0
    total = bid_size + ask_size
    if total <= 0.0:
        return float("nan")
    microprice = (ask_size * best_bid + bid_size * best_ask) / total
    return 10_000.0 * (microprice - midpoint) / midpoint


def _pressure_row(value: object) -> dict[str, float | int]:
    row = _mapping(value, "snapshot")
    bids = _levels(row.get("bids"), "bids")
    asks = _levels(row.get("asks"), "asks")
    best_bid = _finite_number(row.get("best_bid"), "best_bid", positive=True)
    best_ask = _finite_number(row.get("best_ask"), "best_ask", positive=True)
    if best_bid >= best_ask:
        raise ValueError("native L2 best_bid must be below best_ask")
    midpoint = (best_bid + best_ask) / 2.0
    bid_5, ask_5 = _pressure(bids, 5), _pressure(asks, 5)
    bid_20, ask_20 = _pressure(bids, 20), _pressure(asks, 20)
    return {
        "ts_ms": _timestamp(row.get("ts_exchange_ms")),
        "obi_5": _order_pressure(bid_5, ask_5),
        "obi_20": _order_pressure(bid_20, ask_20),
        "spread_bps": 10_000.0 * (best_ask - best_bid) / midpoint,
        "micro_price_delta_bps": _microprice_delta(
            best_bid, best_ask, bids[0][1], asks[0][1]
        ),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "best_bid_size": bids[0][1],
        "best_ask_size": asks[0][1],
    }


def load_native_book_pressure(path: Path | str) -> pd.DataFrame:
    """Load native Hyperliquid L2 into typed pressure features."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"native L2 evidence is missing: {source}")
    rows: list[dict[str, float | int]] = []
    with open_text_reader(source) as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload: object = json.loads(line)
                rows.append(_pressure_row(payload))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(
                    f"invalid native L2 evidence at {source}:{line_number}: {exc}"
                ) from exc
    frame = pd.DataFrame(rows, columns=_PRESSURE_COLUMNS)
    if frame.empty:
        return frame
    frame = frame.sort_values("ts_ms", kind="stable").reset_index(drop=True)
    if frame["ts_ms"].duplicated().any():
        raise ValueError(f"native L2 evidence has duplicate timestamps: {source}")
    return frame


def signal_book_bundles(
    bundles: tuple[OxaArchiveBundle, ...],
    signal_times: pd.DatetimeIndex,
) -> tuple[OxaArchiveBundle, ...]:
    """Return signal-hour and prior-hour bundles for backward-only alignment."""
    selected: set[int] = set()
    python_times = signal_times.to_pydatetime()
    for position, bundle in enumerate(bundles):
        if any(bundle.start <= signal < bundle.end for signal in python_times):
            selected.add(position)
            if position > 0:
                selected.add(position - 1)
    return tuple(bundles[position] for position in sorted(selected))


def load_signal_book_pressure(
    bundles: tuple[OxaArchiveBundle, ...],
    signal_times: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Load only verified book bundles required for decision-time pressure."""
    frames = [
        load_native_book_pressure(bundle.book_path)
        for bundle in signal_book_bundles(bundles, signal_times)
        if bundle.book_path is not None
    ]
    if not frames:
        return pd.DataFrame(columns=_PRESSURE_COLUMNS)
    frame = pd.concat(frames, ignore_index=True)
    frame = frame.sort_values("ts_ms", kind="stable").drop_duplicates("ts_ms")
    return frame.reset_index(drop=True)
