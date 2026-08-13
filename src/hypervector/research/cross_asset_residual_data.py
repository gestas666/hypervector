"""Frozen Hyperliquid inputs for cross-asset residual development."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)
from hypervector.research.low_tf_multi_asset_contract import ordered_frame_sha256

DEVELOPMENT_START = pd.Timestamp("2025-07-28T00:00:00Z")
DEVELOPMENT_END = pd.Timestamp("2026-01-28T00:00:00Z")
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_YEAR_ID = "20250728T000000000000Z_20260728T000000000000Z"


def load_residual_development_inputs(
    data_root: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, dict[str, object]]]:
    """Load exact native minute paths and authentic hourly funding."""
    frames: dict[str, pd.DataFrame] = {}
    identity: dict[str, dict[str, object]] = {}
    for symbol in _SYMBOLS:
        bars_path = data_root / "cache" / f"{symbol}_1m_365d.parquet"
        funding_path = _funding_path(data_root, symbol)
        bars = _load_exact_bars(bars_path)
        funding = load_verified_hourly_funding(
            [funding_path], DEVELOPMENT_START, DEVELOPMENT_END
        )
        frames[symbol] = attach_hourly_funding(
            bars.set_index("timestamp"), funding
        ).reset_index()
        identity[symbol] = build_residual_source_identity(
            bars_path,
            funding_path,
            bars,
        )
    return frames, identity


def _funding_path(data_root: Path, symbol: str) -> Path:
    return (
        data_root
        / "cache"
        / "vendor"
        / "hyperliquid"
        / symbol
        / f"{_YEAR_ID}_funding"
        / "funding.parquet"
    )


def _load_exact_bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"residual source bars do not exist: {path}")
    frame = pd.read_parquet(path)
    times = pd.DatetimeIndex(frame["timestamp"])
    window = frame.loc[(times >= DEVELOPMENT_START) & (times < DEVELOPMENT_END)].copy()
    expected = pd.date_range(
        DEVELOPMENT_START, DEVELOPMENT_END, freq="1min", inclusive="left"
    )
    if not pd.DatetimeIndex(window["timestamp"]).equals(expected):
        raise ValueError(f"residual source does not cover frozen window: {path}")
    return window.reset_index(drop=True)


def build_residual_source_identity(
    bars_path: Path,
    funding_path: Path,
    bars: pd.DataFrame,
) -> dict[str, object]:
    """Bind source files, selected rows, and continuity-fill evidence."""
    sources = bars["source"].astype(str)
    if not sources.isin({"hl", "hl_gap_fill"}).all():
        raise ValueError("residual source identity contains an unknown bar source")
    gaps = sources.eq("hl_gap_fill")
    return {
        "bars_path": str(bars_path),
        "bars": file_evidence(bars_path),
        "funding_path": str(funding_path),
        "funding": file_evidence(funding_path),
        "minute_rows": len(bars),
        "selected_frame_rows": len(bars),
        "selected_frame_sha256": ordered_frame_sha256(
            bars,
            time_column="timestamp",
        ),
        "native_rows": int((~gaps).sum()),
        "gap_fill_rows": int(gaps.sum()),
        "maximum_gap_fill_run": _maximum_true_run(gaps),
        "first_timestamp_utc": pd.Timestamp(bars["timestamp"].iloc[0]).isoformat(),
        "last_timestamp_utc": pd.Timestamp(bars["timestamp"].iloc[-1]).isoformat(),
    }


def _maximum_true_run(mask: pd.Series) -> int:
    if not bool(mask.any()):
        return 0
    groups = mask.ne(mask.shift(fill_value=False)).cumsum()
    return int(mask.groupby(groups).sum().max())
