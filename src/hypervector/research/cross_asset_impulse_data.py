"""Bounded Hyperliquid-native inputs for impulse development research."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cross_asset_impulse_models import CrossAssetImpulseConfig
from hypervector.research.cross_asset_impulse_warmup import (
    reconstruct_impulse_warmup,
)
from hypervector.research.low_tf_multi_asset_contract import ordered_frame_sha256

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_COLUMNS = ["timestamp", "open", "close", "source"]
_SOURCES = {"hl", "hl_gap_fill"}
_PRODUCTION_WARMUP_START = pd.Timestamp("2025-07-20T23:55:00Z")
_PRODUCTION_START = pd.Timestamp("2025-07-28T00:00:00Z")
_REPAIR_START = pd.Timestamp("2025-07-27T00:00:00Z")
_REPAIR_END = pd.Timestamp("2025-07-27T12:03:00Z")


def load_impulse_development_inputs(
    data_root: Path,
    config: CrossAssetImpulseConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, dict[str, object]]]:
    """Load only warmup plus development rows and bind exact source identity."""
    frames: dict[str, pd.DataFrame] = {}
    identity: dict[str, dict[str, object]] = {}
    for symbol in _SYMBOLS:
        path = data_root / "cache" / f"{symbol}_1m_365d.parquet"
        frame, warmup = _load_selected_frame(path, data_root, config, symbol)
        frames[symbol] = frame
        identity[symbol] = _source_identity(path, frame, warmup)
    return frames, identity


def _load_selected_frame(
    path: Path,
    data_root: Path,
    config: CrossAssetImpulseConfig,
    symbol: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"{symbol} impulse source does not exist: {path}")
    frame = pd.read_parquet(
        path,
        columns=_COLUMNS,
        filters=[
            ("timestamp", ">=", config.warmup_start.to_pydatetime()),
            ("timestamp", "<", config.development_end.to_pydatetime()),
        ],
    ).reset_index(drop=True)
    expected = pd.date_range(
        config.warmup_start,
        config.development_end,
        freq="1min",
        inclusive="left",
    )
    if pd.DatetimeIndex(frame["timestamp"]).equals(expected):
        _validate_frame(frame, symbol)
        return frame, {}
    development = pd.date_range(
        config.development_start,
        config.development_end,
        freq="1min",
        inclusive="left",
    )
    if not pd.DatetimeIndex(frame["timestamp"]).equals(development):
        raise ValueError(
            f"{symbol} source does not cover the exact warmup and development window"
        )
    warmup, identity = _reconstructed_warmup(data_root, symbol, config)
    combined = pd.concat([warmup[_COLUMNS], frame], ignore_index=True)
    if not pd.DatetimeIndex(combined["timestamp"]).equals(expected):
        raise ValueError(f"{symbol} reconstructed warmup is not contiguous")
    _validate_frame(combined, symbol)
    return combined, identity


def _validate_frame(frame: pd.DataFrame, symbol: str) -> None:
    sources = frame["source"].astype(str)
    if not sources.isin(_SOURCES).all():
        raise ValueError(f"{symbol} impulse source contains an unsupported source")
    prices = frame[["open", "close"]].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0.0).any():
        raise ValueError(f"{symbol} impulse prices must be positive and finite")


def _reconstructed_warmup(
    data_root: Path,
    symbol: str,
    config: CrossAssetImpulseConfig,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if (
        config.warmup_start != _PRODUCTION_WARMUP_START
        or config.development_start != _PRODUCTION_START
    ):
        raise ValueError(f"{symbol} has no declared reconstructed warmup source")
    candle = _bundle_path(
        data_root, symbol, config.warmup_start, config.development_start, "candles_1m"
    )
    trades = _bundle_path(data_root, symbol, _REPAIR_START, _REPAIR_END, "trades")
    return reconstruct_impulse_warmup(
        candle_bundle=candle,
        trade_bundle=trades,
        symbol=symbol,
        start=config.warmup_start,
        end=config.development_start,
        repair_start=_REPAIR_START,
        repair_end=_REPAIR_END,
    )


def _bundle_path(
    data_root: Path,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    suffix: str,
) -> Path:
    stamp = "%Y%m%dT%H%M%S%fZ"
    window = f"{start.strftime(stamp)}_{end.strftime(stamp)}_{suffix}"
    return (
        data_root / "cache" / "vendor" / "0xarchive" / "hyperliquid" / symbol / window
    )


def _source_identity(
    path: Path,
    frame: pd.DataFrame,
    warmup: dict[str, object],
) -> dict[str, object]:
    sources = frame["source"].astype(str)
    gap = sources.eq("hl_gap_fill")
    identity = {
        "bars_path": str(path),
        "bars": file_evidence(path),
        "selected_rows": len(frame),
        "selected_frame_sha256": ordered_frame_sha256(
            frame,
            time_column="timestamp",
        ),
        "native_rows": int((~gap).sum()),
        "gap_fill_rows": int(gap.sum()),
        "first_timestamp_utc": pd.Timestamp(frame["timestamp"].iloc[0]).isoformat(),
        "last_timestamp_utc": pd.Timestamp(frame["timestamp"].iloc[-1]).isoformat(),
    }
    if warmup:
        identity.update(
            warmup_source_files=warmup["source_files"],
            native_candle_rows=warmup["native_candle_rows"],
            trade_reconstruction_rows=warmup["trade_reconstruction_rows"],
            warmup_gap_fill_rows=warmup["gap_fill_rows"],
        )
    return identity
