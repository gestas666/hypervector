"""Reusable exact-window market inputs for causal strategy screens."""

from __future__ import annotations

from datetime import datetime
import hashlib
import math
from pathlib import Path

import pandas as pd


def load_causal_minute_window(
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load one gap-free minute interval with complete exact-hour funding."""
    return load_causal_bar_window(
        bars_path,
        funding_paths,
        start,
        end,
        bar_timeframe="1min",
    )


def load_causal_bar_window(
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
    *,
    bar_timeframe: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load one gap-free native-bar interval with complete hourly funding."""
    if end <= start:
        raise ValueError("screen end must be after start")
    timeframe = _validated_timeframe(bar_timeframe)
    bars = _indexed_parquet(bars_path)
    bars = bars.loc[(bars.index >= start) & (bars.index < end)].copy()
    _validate_bar_cadence(bars, start, end, timeframe)
    funding = _funding_series(funding_paths, start, end)
    if not funding.index.isin(bars.index).all():
        raise ValueError("funding timestamps do not align with source bars")
    bars["funding_rate"] = 0.0
    bars.loc[funding.index, "funding_rate"] = funding
    return bars, _data_evidence(
        bars_path,
        funding_paths,
        bars,
        funding,
        bar_timeframe=timeframe,
    )


def resample_complete_execution_bars(
    bars: pd.DataFrame,
    timeframe: str,
) -> pd.DataFrame:
    """Build fully completed execution bars without forward information."""
    minutes = timeframe_minutes(timeframe)
    if minutes == 1:
        return bars.copy()
    grouped = bars.resample(timeframe, label="left", closed="left")
    result = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        funding_rate=("funding_rate", "sum"),
    )
    return result.loc[grouped.size().eq(minutes)].dropna()


def timeframe_minutes(timeframe: str) -> int:
    """Return an exact whole-minute duration for one pandas frequency."""
    delta = pd.Timedelta(timeframe)
    minute = pd.Timedelta(minutes=1)
    if delta < minute or delta % minute != pd.Timedelta(0):
        raise ValueError("execution timeframe must be whole positive minutes")
    return int(delta / minute)


def _indexed_parquet(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"screen input is missing: {path}")
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise ValueError(f"screen input has no timestamp: {path}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.set_index("timestamp").sort_index()


def _validated_timeframe(value: str) -> str:
    minutes = timeframe_minutes(value)
    return f"{minutes}min"


def _validate_bar_cadence(
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
    timeframe: str,
) -> None:
    delta = pd.Timedelta(timeframe)
    duration = pd.Timestamp(end) - pd.Timestamp(start)
    if duration % delta != pd.Timedelta(0):
        raise ValueError(f"screen window is not aligned to {timeframe} cadence")
    expected = pd.date_range(start, end, freq=timeframe, inclusive="left")
    if not bars.index.is_unique or not bars.index.equals(expected):
        raise ValueError(f"screen bar window is not complete at {timeframe} cadence")


def _funding_series(
    paths: list[Path],
    start: datetime,
    end: datetime,
) -> pd.Series:
    frames = [_indexed_parquet(path) for path in paths]
    funding = pd.concat(frames).sort_index()
    if funding.index.duplicated().any():
        duplicates = funding.loc[funding.index.duplicated(keep=False), "funding_rate"]
        if duplicates.groupby(level=0).nunique().gt(1).any():
            raise ValueError("funding bundles contain conflicting duplicate rates")
        funding = funding.loc[~funding.index.duplicated(keep="first")]
    expected = pd.date_range(start, end, freq="1h", inclusive="left")
    series = funding["funding_rate"].astype(float).reindex(expected)
    if series.isna().any() or not series.map(math.isfinite).all():
        raise ValueError("screen funding is incomplete or non-finite")
    return series


def _data_evidence(
    bars_path: Path,
    funding_paths: list[Path],
    bars: pd.DataFrame,
    funding: pd.Series,
    *,
    bar_timeframe: str,
) -> dict[str, object]:
    return {
        "bars_path": str(bars_path.resolve()),
        "bars_sha256": _sha256(bars_path),
        "funding_paths": [str(path.resolve()) for path in funding_paths],
        "funding_sha256": [_sha256(path) for path in funding_paths],
        "bar_rows": len(bars),
        "bar_timeframe": bar_timeframe,
        "gap_fill_rows": int(
            bars.get("source", pd.Series(dtype=str)).eq("hl_gap_fill").sum()
        ),
        "funding_events": len(funding),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
