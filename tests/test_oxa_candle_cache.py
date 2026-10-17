"""Offline regression checks for one-minute research-cache installation."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from hypervector.cli_oxa_candle_cache import install_candle_cache


def _args(tmp_path: Path, *, minutes: int = 1440) -> argparse.Namespace:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    return argparse.Namespace(
        data_root=tmp_path,
        symbol="xyz:SNDK",
        timeframe="1m",
        start=start,
        end=start + timedelta(minutes=minutes),
    )


def test_minute_cache_retains_exact_rows_and_labels_only_missing_bar(
    tmp_path: Path,
) -> None:
    """The extracted helper preserves actual minute data and labeled repairs."""
    args = _args(tmp_path)
    timestamps = pd.date_range(args.start, args.end, freq="1min", inclusive="left")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 2.0,
            "source": "hl",
        }
    )
    source = tmp_path / "candles.parquet"
    frame.drop(index=10).to_parquet(source, index=False)

    path, repaired = install_candle_cache(args, {"candles_path": str(source)})

    actual = pd.read_parquet(path)
    assert repaired == 1
    assert len(actual) == 1440
    assert actual.iloc[10]["source"] == "hl_gap_fill"
    assert actual.iloc[10]["volume"] == 0
    pd.testing.assert_frame_equal(actual.drop(index=10), frame.drop(index=10))


@pytest.mark.parametrize("minutes", [1, 1439])
def test_cache_rejects_partial_day_before_reading_source(
    tmp_path: Path,
    minutes: int,
) -> None:
    """No file access is required to reject an unsupported duration."""
    with pytest.raises(ValueError, match="whole-day"):
        install_candle_cache(_args(tmp_path, minutes=minutes), {})


def test_cache_requires_explicit_acquired_file_path(tmp_path: Path) -> None:
    """Missing provenance output cannot silently install an empty cache."""
    with pytest.raises(ValueError, match="did not return a Parquet path"):
        install_candle_cache(_args(tmp_path), {})


def test_direct_cache_helper_rejects_nonminute_interval(tmp_path: Path) -> None:
    """The helper also guards callers that bypass CLI validation."""
    args = _args(tmp_path)
    args.timeframe = "15m"
    with pytest.raises(ValueError, match="requires --timeframe 1m"):
        install_candle_cache(args, {})
