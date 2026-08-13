"""Verified all-asset inputs for the 15-minute Swing/HA experiment."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.research.low_tf_multi_asset_contract import (
    complete_ohlcv_bars,
    default_low_tf_contract,
)
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)

_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"


@dataclass(frozen=True)
class SwingHaAssetInput:
    """Explicit native-perpetual candle and funding paths."""

    symbol: str
    venue_max_leverage: float
    bars_path: Path
    funding_path: Path


@dataclass(frozen=True)
class SwingHaAssetData:
    """Verified funded 15-minute bars and immutable source identity."""

    symbol: str
    venue_max_leverage: float
    bars: pd.DataFrame
    source_identity: dict[str, object]


def default_asset_inputs(data_root: Path) -> tuple[SwingHaAssetInput, ...]:
    """Return the frozen one-year BTC/ETH/SOL/HYPE source paths."""
    return tuple(
        SwingHaAssetInput(
            asset.symbol,
            asset.venue_max_leverage,
            data_root / "cache" / f"{asset.symbol}_1m_365d.parquet",
            data_root
            / "cache"
            / "vendor"
            / "hyperliquid"
            / asset.symbol
            / f"{_YEAR_ID}_funding"
            / "funding.parquet",
        )
        for asset in default_low_tf_contract().assets
    )


def load_asset_data(source: SwingHaAssetInput) -> SwingHaAssetData:
    """Load one exact one-year source and build funded complete 15-minute bars."""
    minutes = _load_minutes(source.bars_path)
    native = complete_ohlcv_bars(minutes, source_minutes=1, bar_minutes=15)
    gaps = _gap_flags(minutes)
    indexed = native.set_index("bar_open_at")
    if not indexed.index.equals(gaps.index):
        raise RuntimeError("Swing/HA native bars and gap flags are misaligned")
    indexed["gap_fill_touched"] = gaps.to_numpy(dtype=bool)
    end = indexed.index.max() + pd.Timedelta(minutes=15)
    funding = load_verified_hourly_funding(
        [source.funding_path], indexed.index.min(), end
    )
    funded = attach_hourly_funding(indexed, funding)
    identity = _source_identity(source, minutes, funded, funding)
    return SwingHaAssetData(source.symbol, source.venue_max_leverage, funded, identity)


def _load_minutes(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Swing/HA candle source does not exist: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Swing/HA minute source missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Swing/HA minute times must be aware, ordered, and unique")
    prices = frame[["open", "high", "low", "close", "volume"]].to_numpy(float)
    if not np.isfinite(prices).all() or (prices[:, :4] <= 0.0).any():
        raise ValueError("Swing/HA minute prices must be finite and positive")
    if not frame["source"].isin({"hl", "hl_gap_fill"}).all():
        raise ValueError("Swing/HA minute source contains a non-Hyperliquid row")
    return frame.reset_index(drop=True)


def _gap_flags(minutes: pd.DataFrame) -> pd.Series:
    indexed = minutes.set_index("timestamp")
    groups = (
        indexed["source"]
        .eq("hl_gap_fill")
        .resample("15min", label="left", closed="left")
    )
    counts = indexed["close"].resample("15min", label="left", closed="left").count()
    return groups.max().loc[counts.eq(15)].rename("gap_fill_touched")


def _source_identity(
    source: SwingHaAssetInput,
    minutes: pd.DataFrame,
    bars: pd.DataFrame,
    funding: pd.Series,
) -> dict[str, object]:
    return {
        "symbol": source.symbol,
        "bars_path": str(source.bars_path.resolve()),
        "bars_sha256": _file_sha256(source.bars_path),
        "funding_path": str(source.funding_path.resolve()),
        "funding_sha256": _file_sha256(source.funding_path),
        "minute_rows": len(minutes),
        "gap_fill_minute_rows": int(minutes["source"].eq("hl_gap_fill").sum()),
        "native_15m_rows": len(bars),
        "gap_touched_15m_rows": int(bars["gap_fill_touched"].sum()),
        "funding_events": len(funding),
        "start_utc": bars.index.min().isoformat(),
        "end_utc_exclusive": (bars.index.max() + pd.Timedelta(minutes=15)).isoformat(),
        "execution_authority": "none",
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
