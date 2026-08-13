"""Data integrity contracts for Market Cipher venue inputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)


def _funding(path: Path, timestamps: list[str], rates: list[float]) -> Path:
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, utc=True),
            "funding_rate": rates,
            "source": ["hl_funding_history"] * len(rates),
        }
    ).to_parquet(path, index=False)
    return path


def test_overlapping_funding_files_deduplicate_identical_rows(tmp_path: Path) -> None:
    """Overlapping archive requests may repeat but may not disagree."""
    first = _funding(
        tmp_path / "first.parquet",
        ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
        [0.001, 0.002],
    )
    second = _funding(
        tmp_path / "second.parquet",
        ["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"],
        [0.002, 0.003],
    )

    result = load_verified_hourly_funding(
        [first, second],
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-01T03:00:00Z"),
    )

    assert result.tolist() == [0.001, 0.002, 0.003]


def test_missing_hourly_funding_fails_instead_of_becoming_zero(tmp_path: Path) -> None:
    """A silent zero must not replace absent venue funding evidence."""
    path = _funding(
        tmp_path / "funding.parquet",
        ["2026-01-01T00:00:00Z", "2026-01-01T02:00:00Z"],
        [0.001, 0.003],
    )

    with pytest.raises(ValueError, match="funding coverage missing 1 hourly rows"):
        load_verified_hourly_funding(
            [path],
            pd.Timestamp("2026-01-01T00:00:00Z"),
            pd.Timestamp("2026-01-01T03:00:00Z"),
        )


def test_funding_attaches_only_to_exact_settlement_bar() -> None:
    """A known hourly settlement is charged once, not smeared across bars."""
    index = pd.date_range("2026-01-01", periods=8, freq="15min", tz="UTC")
    bars = pd.DataFrame({"close": [100.0] * 8}, index=index)
    rates = pd.Series(
        [0.001, -0.002],
        index=pd.DatetimeIndex([index[0], index[4]]),
        dtype=float,
    )

    result = attach_hourly_funding(bars, rates)

    assert result["funding_rate"].tolist() == [
        0.001,
        0.0,
        0.0,
        0.0,
        -0.002,
        0.0,
        0.0,
        0.0,
    ]
