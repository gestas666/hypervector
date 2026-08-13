"""Verified Hyperliquid funding inputs for Market Cipher research."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_FUNDING_COLUMNS = {"timestamp", "funding_rate", "source"}


def load_verified_hourly_funding(
    paths: list[Path],
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> pd.Series:
    """Load complete authentic hourly funding from explicit parquet files."""
    start, end = _validated_window(start_utc, end_utc)
    if not paths:
        raise ValueError("at least one funding parquet path is required")
    frames = [_read_funding(path) for path in paths]
    combined = pd.concat(frames, ignore_index=True)
    combined = _deduplicate_funding(combined)
    expected = pd.date_range(start.ceil("h"), end, freq="h", inclusive="left")
    selected = combined.set_index("timestamp")["funding_rate"].reindex(expected)
    missing = int(selected.isna().sum())
    if missing:
        raise ValueError(f"funding coverage missing {missing} hourly rows")
    return selected.astype(float).rename("funding_rate")


def attach_hourly_funding(bars: pd.DataFrame, funding: pd.Series) -> pd.DataFrame:
    """Attach each exact hourly settlement to one matching strategy bar."""
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("funding attachment requires timezone-aware bar index")
    if not isinstance(funding.index, pd.DatetimeIndex) or funding.index.tz is None:
        raise ValueError("funding rates require timezone-aware timestamps")
    missing = funding.index.difference(bars.index)
    in_span = missing[(missing >= bars.index.min()) & (missing <= bars.index.max())]
    if len(in_span):
        raise ValueError(
            f"{len(in_span)} funding settlements have no matching strategy bar"
        )
    output = bars.copy()
    output["funding_rate"] = 0.0
    common = funding.index.intersection(output.index)
    output.loc[common, "funding_rate"] = funding.loc[common].to_numpy(float)
    return output


def _validated_window(
    start_utc: pd.Timestamp, end_utc: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = pd.Timestamp(start_utc), pd.Timestamp(end_utc)
    if start.tz is None or end.tz is None:
        raise ValueError("funding window timestamps must be timezone-aware")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    if start >= end:
        raise ValueError("funding window start must precede end")
    return start, end


def _read_funding(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"funding parquet does not exist: {path}")
    frame = pd.read_parquet(path)
    missing = sorted(_FUNDING_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"funding parquet missing columns: {missing}")
    output = frame.loc[:, ["timestamp", "funding_rate", "source"]].copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True)
    output["funding_rate"] = pd.to_numeric(output["funding_rate"], errors="raise")
    if output.empty or not np.isfinite(output["funding_rate"]).all():
        raise ValueError("funding parquet contains no finite rates")
    if not output["source"].eq("hl_funding_history").all():
        raise ValueError("funding parquet contains an unverified source")
    return output


def _deduplicate_funding(frame: pd.DataFrame) -> pd.DataFrame:
    conflicts = frame.groupby("timestamp")["funding_rate"].nunique().gt(1)
    if bool(conflicts.any()):
        count = int(conflicts.sum())
        raise ValueError(f"funding overlap has {count} conflicting timestamps")
    return frame.drop_duplicates("timestamp").sort_values("timestamp")
