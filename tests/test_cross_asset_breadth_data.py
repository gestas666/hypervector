"""Source-grid and 15-minute construction tests for breadth research."""

import numpy as np
import pandas as pd
import pytest

from hypervector.research.cross_asset_breadth_data import build_breadth_15m_frames
from hypervector.research.cross_asset_breadth_models import CrossAssetBreadthConfig


def _minute_frames(periods: int = 30) -> dict[str, pd.DataFrame]:
    timestamps = pd.date_range("2025-07-28T00:00:00Z", periods=periods, freq="1min")
    frames: dict[str, pd.DataFrame] = {}
    for offset, symbol in enumerate(("BTC", "ETH", "SOL", "HYPE"), start=1):
        prices = 100.0 * offset + np.arange(periods, dtype=float) * 0.01
        frames[symbol] = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": prices,
                "close": prices + 0.005,
                "source": "hl",
            }
        )
    return frames


def test_builds_completed_fifteen_minute_closes_and_validity() -> None:
    frames = _minute_frames()
    frames["SOL"].loc[20, "source"] = "hl_gap_fill"

    closes, validity = build_breadth_15m_frames(
        frames,
        CrossAssetBreadthConfig(),
    )

    assert list(closes.columns) == ["BTC", "ETH", "SOL", "HYPE"]
    assert closes.index.tolist() == [
        pd.Timestamp("2025-07-28T00:00:00Z"),
        pd.Timestamp("2025-07-28T00:15:00Z"),
    ]
    assert closes.loc[pd.Timestamp("2025-07-28T00:00:00Z"), "BTC"] == pytest.approx(
        frames["BTC"].loc[14, "close"]
    )
    assert validity.loc[pd.Timestamp("2025-07-28T00:00:00Z")].all()
    assert validity.loc[pd.Timestamp("2025-07-28T00:15:00Z"), "BTC"]
    assert not validity.loc[pd.Timestamp("2025-07-28T00:15:00Z"), "SOL"]


def test_rejects_unequal_or_noncontiguous_source_grids() -> None:
    frames = _minute_frames()
    frames["ETH"] = frames["ETH"].drop(index=10).reset_index(drop=True)

    with pytest.raises(ValueError, match="same contiguous minute grid"):
        build_breadth_15m_frames(frames, CrossAssetBreadthConfig())


def test_partial_fifteen_minute_groups_are_not_admitted() -> None:
    frames = _minute_frames(periods=31)

    closes, validity = build_breadth_15m_frames(
        frames,
        CrossAssetBreadthConfig(),
    )

    assert len(closes) == 3
    assert not validity.iloc[-1].any()
