"""Source-bound warmup reconstruction for cross-asset impulse research."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.data.oxa_storage import file_evidence, verify_file_evidence
from hypervector.data.oxa_trade_candle_audit import trade_rows_to_minute_bars
from hypervector.data.oxa_trades import (
    TRADE_NORMALIZATION_VERSION,
    load_trade_jsonl,
)

_PRICE_TOLERANCE = 1e-9


def reconstruct_impulse_warmup(
    *,
    candle_bundle: Path,
    trade_bundle: Path,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    repair_start: pd.Timestamp,
    repair_end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Reconstruct missing native candles from a complete venue trade tape."""
    _validate_bounds(start, end, repair_start, repair_end)
    candle_manifest = _verified_manifest(
        candle_bundle,
        _candle_identity(symbol, start, end),
        "candle bundle identity",
    )
    trade_manifest = _verified_manifest(
        trade_bundle,
        _trade_identity(symbol, repair_start, repair_end),
        "trade bundle identity",
    )
    candles = _load_candles(candle_bundle / "candles.parquet", start, end)
    candle_count = _count(candle_manifest.get("row_count"), "candle row count")
    if len(candles) != candle_count:
        raise ValueError("candle bundle row count differs from manifest")
    trades = load_trade_jsonl(trade_bundle / "trades.jsonl.gz")
    if len(trades) != _count(trade_manifest.get("trade_count"), "trade count"):
        raise ValueError("trade bundle row count differs from manifest")
    trade_bars = trade_rows_to_minute_bars(trades)
    if not trade_bars.empty and (
        trade_bars.index.min() < repair_start or trade_bars.index.max() >= repair_end
    ):
        raise ValueError("trade row lies outside declared repair window")
    frame, counts = _reconstruct(candles, trade_bars, start, end)
    identity = {
        **counts,
        "source_files": _source_files(candle_bundle, trade_bundle),
        "candle_manifest_row_count": candle_count,
        "trade_manifest_row_count": len(trades),
    }
    return frame, identity


def _verified_manifest(
    bundle: Path, expected: dict[str, object], label: str
) -> dict[str, object]:
    path = bundle / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"{label} manifest is missing: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} manifest must be an object")
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{label} differs from requested source")
    verify_file_evidence(bundle, payload.get("files"))
    return payload


def _candle_identity(
    symbol: str, start: pd.Timestamp, end: pd.Timestamp
) -> dict[str, object]:
    return {
        "source": "0xarchive_hyperliquid_candles",
        "symbol": symbol,
        "interval": "1m",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "complete": True,
    }


def _trade_identity(
    symbol: str, start: pd.Timestamp, end: pd.Timestamp
) -> dict[str, object]:
    return {
        "source": "0xarchive_hyperliquid_public_trades",
        "symbol": symbol,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "normalization_version": TRADE_NORMALIZATION_VERSION,
        "surrogate_trade_id_count": 0,
        "unresolved_fill_groups": 0,
        "complete": True,
    }


def _load_candles(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise ValueError("warmup candle bundle is missing price columns")
    times = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    if not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError("warmup candle timestamps must be ordered and unique")
    if ((times < start) | (times >= end)).any():
        raise ValueError("warmup candle row lies outside requested bounds")
    prices = frame[["open", "high", "low", "close"]].to_numpy(float)
    if not np.isfinite(prices).all() or (prices <= 0.0).any():
        raise ValueError("warmup candle prices must be positive and finite")
    return frame.set_index(times)


def _reconstruct(
    candles: pd.DataFrame,
    trades: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, int]]:
    expected = pd.date_range(start, end, freq="1min", inclusive="left")
    native = candles.reindex(expected)
    tape = trades.reindex(expected)
    _validate_overlap(native, tape)
    native_present = native["open"].notna()
    trade_present = tape["trade_open"].notna()
    output = pd.DataFrame(index=expected)
    for name in ("open", "high", "low", "close"):
        output[name] = native[name].combine_first(tape[f"trade_{name}"])
    missing = ~native_present & ~trade_present
    carry = output["close"].ffill()
    for name in ("open", "high", "low", "close"):
        output.loc[missing, name] = carry.loc[missing]
    if output[["open", "high", "low", "close"]].isna().any(axis=None):
        raise ValueError("cannot reconstruct a leading warmup minute")
    output["source"] = "hl"
    output.loc[missing, "source"] = "hl_gap_fill"
    output.index.name = "timestamp"
    counts = {
        "native_candle_rows": int(native_present.sum()),
        "trade_reconstruction_rows": int((~native_present & trade_present).sum()),
        "gap_fill_rows": int(missing.sum()),
    }
    return output.reset_index(), counts


def _validate_overlap(native: pd.DataFrame, trades: pd.DataFrame) -> None:
    overlap = native["open"].notna() & trades["trade_open"].notna()
    selected = pd.DataFrame(
        {
            "native_high": native.loc[overlap, "high"],
            "native_low": native.loc[overlap, "low"],
            "trade_high": trades.loc[overlap, "trade_high"],
            "trade_low": trades.loc[overlap, "trade_low"],
            "minutes": 1,
        }
    )
    grouped = selected.resample("5min").agg(
        native_high=("native_high", "max"),
        native_low=("native_low", "min"),
        trade_high=("trade_high", "max"),
        trade_low=("trade_low", "min"),
        minutes=("minutes", "sum"),
    )
    complete = grouped["minutes"].eq(5)
    mismatch = complete & (
        (grouped["native_high"] - grouped["trade_high"]).abs().gt(_PRICE_TOLERANCE)
        | (grouped["native_low"] - grouped["trade_low"]).abs().gt(_PRICE_TOLERANCE)
    )
    if mismatch.any():
        first = pd.Timestamp(grouped.index[mismatch][0]).isoformat()
        raise ValueError(f"warmup trade/candle price mismatch at {first}")


def _source_files(candle_bundle: Path, trade_bundle: Path) -> list[dict[str, object]]:
    paths = (
        candle_bundle / "candles.parquet",
        candle_bundle / "manifest.json",
        trade_bundle / "trades.jsonl.gz",
        trade_bundle / "manifest.json",
    )
    return [{"path": str(path), **file_evidence(path)} for path in paths]


def _validate_bounds(
    start: pd.Timestamp,
    end: pd.Timestamp,
    repair_start: pd.Timestamp,
    repair_end: pd.Timestamp,
) -> None:
    if any(value.tz is None for value in (start, end, repair_start, repair_end)):
        raise ValueError("warmup bounds must be timezone-aware")
    if not start < repair_start < repair_end <= end:
        raise ValueError("trade repair bounds must lie inside warmup bounds")


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value
