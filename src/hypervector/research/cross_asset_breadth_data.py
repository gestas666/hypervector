"""Source-bound Hyperliquid inputs for cross-sectional breadth research."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_breadth_models import CrossAssetBreadthConfig
from hypervector.research.cross_asset_impulse_data import (
    load_impulse_development_inputs,
)
from hypervector.research.cross_asset_impulse_models import CrossAssetImpulseConfig

_REQUIRED_COLUMNS = {"timestamp", "open", "close", "source"}


@dataclass(frozen=True)
class BreadthDevelopmentInputs:
    """Source frames, completed-bar features, and immutable identities."""

    minute_frames: dict[str, pd.DataFrame]
    closes_15m: pd.DataFrame
    validity_15m: pd.DataFrame
    source_identity: dict[str, dict[str, object]]


def load_breadth_development_inputs(
    data_root: Path,
    config: CrossAssetBreadthConfig,
) -> BreadthDevelopmentInputs:
    """Load the exact repaired venue grid and construct completed 15m bars."""
    source_config = CrossAssetImpulseConfig(
        warmup_start=config.warmup_start,
        development_start=config.development_start,
        development_end=config.development_end,
    )
    frames, identity = load_impulse_development_inputs(data_root, source_config)
    closes, validity = build_breadth_15m_frames(frames, config)
    return BreadthDevelopmentInputs(frames, closes, validity, identity)


def build_breadth_15m_frames(
    minute_frames: dict[str, pd.DataFrame],
    config: CrossAssetBreadthConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resample an exact four-symbol minute grid without admitting gaps."""
    frames = _validated_minute_frames(minute_frames, config)
    closes: dict[str, pd.Series] = {}
    validity: dict[str, pd.Series] = {}
    frequency = f"{config.bar_minutes}min"
    for symbol in config.symbols:
        indexed = frames[symbol].set_index("timestamp")
        groups = indexed.resample(frequency, label="left", closed="left")
        closes[symbol] = groups["close"].last()
        count = groups["close"].count()
        native = (
            indexed["source"]
            .eq("hl")
            .resample(frequency, label="left", closed="left")
            .sum()
        )
        validity[symbol] = count.eq(config.bar_minutes) & native.eq(config.bar_minutes)
    return pd.DataFrame(closes), pd.DataFrame(validity).astype(bool)


def _validated_minute_frames(
    minute_frames: dict[str, pd.DataFrame],
    config: CrossAssetBreadthConfig,
) -> dict[str, pd.DataFrame]:
    if tuple(minute_frames) != config.symbols:
        raise ValueError("breadth source symbols differ from the frozen universe")
    selected: dict[str, pd.DataFrame] = {}
    reference: pd.DatetimeIndex | None = None
    for symbol in config.symbols:
        frame = minute_frames[symbol].copy()
        missing = _REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            raise ValueError(f"{symbol} source missing columns: {sorted(missing)}")
        index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
        if not _is_contiguous(index) or (
            reference is not None and not index.equals(reference)
        ):
            raise ValueError(
                "breadth sources must share the same contiguous minute grid"
            )
        prices = frame[["open", "close"]].to_numpy(dtype=float)
        if not np.isfinite(prices).all() or (prices <= 0.0).any():
            raise ValueError(f"{symbol} source prices must be positive and finite")
        frame["timestamp"] = index
        selected[symbol] = frame
        reference = index
    return selected


def _is_contiguous(index: pd.DatetimeIndex) -> bool:
    if index.empty or not index.is_unique or not index.is_monotonic_increasing:
        return False
    expected = pd.date_range(index[0], periods=len(index), freq="1min")
    return index.equals(expected)
