"""Tests for causal exact-window strategy-screen inputs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.causal_screen_inputs import load_causal_bar_window


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    bars_path = tmp_path / "bars.parquet"
    funding_path = tmp_path / "funding.parquet"
    timestamps = pd.date_range("2026-01-01", periods=4, freq="15min", tz="UTC")
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1.0, 2.0, 3.0, 4.0],
            "source": ["hl"] * 4,
        }
    ).to_parquet(bars_path, index=False)
    pd.DataFrame(
        {
            "timestamp": [timestamps[0]],
            "funding_rate": [0.00001],
            "source": ["hl_funding_history"],
        }
    ).to_parquet(funding_path, index=False)
    return bars_path, funding_path


def test_load_causal_bar_window_accepts_exact_native_fifteen_minute_data(
    tmp_path: Path,
) -> None:
    """Native 15-minute evidence must not be fabricated into minute bars."""
    bars_path, funding_path = _write_inputs(tmp_path)

    bars, evidence = load_causal_bar_window(
        bars_path,
        [funding_path],
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, 1, tzinfo=UTC),
        bar_timeframe="15min",
    )

    assert len(bars) == 4
    assert bars["funding_rate"].tolist() == pytest.approx([0.00001, 0.0, 0.0, 0.0])
    assert evidence["bar_timeframe"] == "15min"


def test_load_causal_bar_window_rejects_a_missing_native_bar(
    tmp_path: Path,
) -> None:
    """A missing 15-minute bar must remain an explicit technical failure."""
    bars_path, funding_path = _write_inputs(tmp_path)
    bars = pd.read_parquet(bars_path).drop(index=2)
    bars.to_parquet(bars_path, index=False)

    with pytest.raises(ValueError, match="complete at 15min cadence"):
        load_causal_bar_window(
            bars_path,
            [funding_path],
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, 1, tzinfo=UTC),
            bar_timeframe="15min",
        )
