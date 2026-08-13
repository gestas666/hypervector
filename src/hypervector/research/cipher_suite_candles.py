"""Manifest-bound venue candle inputs for causal Cipher research."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_candles import repair_candle_cadence
from hypervector.data.oxa_storage import file_evidence, verify_file_evidence
from hypervector.research.cipher_suite_duckdb import (
    CIPHER_RESEARCH_SYMBOLS,
    CipherOhlcvInputs,
    validate_cipher_ohlcv_coverage,
)
from hypervector.research.hypertrader_source_adapter import (
    resample_hyperliquid_5m,
)

_FIVE_MINUTES = timedelta(minutes=5)
_MAX_GAP_MINUTES = 30


def load_cipher_ohlcv_from_candle_bundle(
    bundle: Path,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    history_bars: int,
    horizon_bars: int,
) -> tuple[CipherOhlcvInputs, dict[str, object]]:
    """Load exact bounded OHLCV from one verified 0xArchive candle bundle."""
    normalized = symbol.strip().upper()
    _validate_request(normalized, start_utc, end_utc, history_bars, horizon_bars)
    query_start = start_utc - _FIVE_MINUTES * history_bars
    query_end = end_utc + _FIVE_MINUTES * horizon_bars
    manifest = _verified_manifest(bundle, normalized, query_start, query_end)
    native = pd.read_parquet(bundle / "candles.parquet")
    _validate_row_count(native, manifest)
    requested_start = _timestamp(manifest["requested_start"], "requested_start")
    requested_end = _timestamp(manifest["requested_end"], "requested_end")
    repaired, total_fills = repair_candle_cadence(
        native,
        start=requested_start.to_pydatetime(),
        end=requested_end.to_pydatetime(),
        max_gap_minutes=_MAX_GAP_MINUTES,
    )
    bounded = repaired.loc[
        repaired["timestamp"].ge(query_start) & repaired["timestamp"].lt(query_end)
    ].copy()
    indexed = bounded.set_index("timestamp").loc[
        :, ["open", "high", "low", "close", "volume"]
    ]
    bars = (
        resample_hyperliquid_5m(indexed)
        .reset_index()
        .rename(columns={"timestamp": "bar_open_at"})
    )
    validate_cipher_ohlcv_coverage(bars, query_start, end_utc, horizon_bars)
    bounded_fills = int(bounded["source"].eq("hl_gap_fill").sum())
    evidence = {
        "source": "0xarchive_hyperliquid_candles",
        "symbol": normalized,
        "bundle": str(bundle.resolve()),
        "manifest": file_evidence(bundle / "manifest.json"),
        "candles": file_evidence(bundle / "candles.parquet"),
        "native_rows": len(native),
        "total_gap_fill_rows": total_fills,
        "gap_fill_rows": bounded_fills,
    }
    return CipherOhlcvInputs(bars, query_start, query_end), evidence


def _validate_request(
    symbol: str,
    start: datetime,
    end: datetime,
    history_bars: int,
    horizon_bars: int,
) -> None:
    if symbol not in CIPHER_RESEARCH_SYMBOLS:
        raise ValueError("unsupported Cipher candle symbol")
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Cipher candle window must be aware and ordered")
    if history_bars < 200 or horizon_bars < 1:
        raise ValueError("Cipher candles require warmup and lookahead")


def _verified_manifest(
    bundle: Path,
    symbol: str,
    query_start: datetime,
    query_end: datetime,
) -> dict[str, object]:
    path = bundle / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Cipher candle manifest is missing: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Cipher candle manifest must be an object")
    identity = {
        "source": "0xarchive_hyperliquid_candles",
        "symbol": symbol,
        "interval": "1m",
        "complete": True,
    }
    if any(payload.get(key) != value for key, value in identity.items()):
        raise ValueError("Cipher candle manifest identity mismatch")
    requested_start = _timestamp(payload.get("requested_start"), "requested_start")
    requested_end = _timestamp(payload.get("requested_end"), "requested_end")
    if requested_start > query_start or requested_end < query_end:
        raise ValueError("Cipher candle bundle has incomplete bounded coverage")
    files = payload.get("files")
    candle_evidence = files.get("candles.parquet") if isinstance(files, dict) else None
    verify_file_evidence(bundle, {"candles.parquet": candle_evidence})
    return payload


def _timestamp(value: object, label: str) -> pd.Timestamp:
    if not isinstance(value, str):
        raise ValueError(f"Cipher candle {label} must be text")
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f"Cipher candle {label} must include a timezone")
    return timestamp.tz_convert("UTC")


def _validate_row_count(frame: pd.DataFrame, manifest: dict[str, object]) -> None:
    count = manifest.get("row_count")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(frame):
        raise ValueError("Cipher candle row count differs from manifest")
