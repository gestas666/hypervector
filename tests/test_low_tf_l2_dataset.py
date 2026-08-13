"""Tests for causal low-timeframe price and L2 feature assembly."""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd
import pytest

from hypervector.research.low_tf_l2_dataset import (
    LowTimeframeDatasetConfig,
    build_low_timeframe_dataset,
)


EXPECTED_FEATURES = {
    "return_1_bps",
    "return_3_bps",
    "return_12_bps",
    "realized_vol_12_bps",
    "range_bps",
    "volume_z_36",
    "trade_flow_imbalance",
    "trade_count_z_36",
    "imbalance_5_last",
    "imbalance_5_mean_60s",
    "imbalance_5_delta_60s",
    "imbalance_10_last",
    "spread_bps_last",
    "micro_price_delta_bps",
    "log_depth_10",
}


def _frames(rows: int = 40) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    opens = pd.date_range("2026-01-01", periods=rows, freq="5min", tz=UTC)
    close = pd.Series(100.0 + np.arange(rows, dtype=float), index=opens)
    bars = pd.DataFrame(
        {
            "bar_open_at": opens,
            "open": close.to_numpy() - 0.25,
            "high": close.to_numpy() + 0.5,
            "low": close.to_numpy() - 0.75,
            "close": close.to_numpy(),
            "volume": 10.0 + np.arange(rows, dtype=float),
            "trade_count": 20 + np.arange(rows),
        }
    )
    trades = pd.DataFrame(
        {
            "bar_open_at": opens,
            "buy_volume": 7.0 + np.arange(rows, dtype=float),
            "sell_volume": 3.0 + np.arange(rows, dtype=float),
        }
    )
    books = pd.DataFrame(
        {
            "bar_open_at": opens,
            "last_book_at": opens + pd.Timedelta(minutes=5),
            "imbalance_5_last": np.linspace(-0.2, 0.2, rows),
            "imbalance_5_mean_60s": np.linspace(-0.1, 0.1, rows),
            "imbalance_5_delta_60s": np.full(rows, 0.01),
            "imbalance_10_last": np.linspace(-0.3, 0.3, rows),
            "spread_bps_last": np.full(rows, 0.2),
            "micro_price_delta_bps": np.full(rows, 0.05),
            "bid_depth_10_last": np.full(rows, 20.0),
            "ask_depth_10_last": np.full(rows, 10.0),
        }
    )
    return bars, trades, books


def test_dataset_is_point_in_time_and_contains_frozen_features() -> None:
    """Completed-bar features must not consume a future book observation."""
    bars, trades, books = _frames()

    dataset = build_low_timeframe_dataset(
        bars,
        trades,
        books,
        LowTimeframeDatasetConfig(symbol="BTC"),
    )

    assert EXPECTED_FEATURES.issubset(dataset.feature_names)
    assert len(dataset.rows) == 4
    assert dataset.rows["symbol"].eq("BTC").all()
    assert (
        dataset.rows["available_at_utc"]
        == dataset.rows["bar_open_at"] + pd.Timedelta(minutes=5)
    ).all()
    assert (dataset.rows["last_book_at"] <= dataset.rows["available_at_utc"]).all()
    assert np.isfinite(dataset.rows[list(dataset.feature_names)].to_numpy()).all()


@pytest.mark.parametrize("frame_name", ["bars", "trades", "books"])
def test_dataset_rejects_unordered_inputs(frame_name: str) -> None:
    """Ordering defects must fail instead of being silently sorted."""
    bars, trades, books = _frames()
    frames = {"bars": bars, "trades": trades, "books": books}
    frames[frame_name] = frames[frame_name].iloc[::-1].reset_index(drop=True)

    with pytest.raises(ValueError, match="ordered"):
        build_low_timeframe_dataset(
            frames["bars"],
            frames["trades"],
            frames["books"],
            LowTimeframeDatasetConfig(symbol="BTC"),
        )


def test_dataset_rejects_duplicate_bar_identity() -> None:
    """One symbol and bar-open timestamp must identify exactly one feature row."""
    bars, trades, books = _frames()
    bars.loc[1, "bar_open_at"] = bars.loc[0, "bar_open_at"]

    with pytest.raises(ValueError, match="duplicate"):
        build_low_timeframe_dataset(
            bars,
            trades,
            books,
            LowTimeframeDatasetConfig(symbol="BTC"),
        )


def test_dataset_rejects_future_book_snapshot() -> None:
    """A book observation after decision availability is look-ahead leakage."""
    bars, trades, books = _frames()
    books.loc[39, "last_book_at"] += pd.Timedelta(milliseconds=1)

    with pytest.raises(ValueError, match="future book"):
        build_low_timeframe_dataset(
            bars,
            trades,
            books,
            LowTimeframeDatasetConfig(symbol="BTC"),
        )


def test_dataset_excludes_missing_same_bar_book_without_forward_fill() -> None:
    """A missing L2 bar must remove that decision rather than borrow a book."""
    bars, trades, books = _frames(rows=42)
    missing_at = books.loc[39, "bar_open_at"]
    books = books.loc[books["bar_open_at"].ne(missing_at)].reset_index(drop=True)

    dataset = build_low_timeframe_dataset(
        bars,
        trades,
        books,
        LowTimeframeDatasetConfig(symbol="BTC"),
    )

    assert dataset.excluded_book_bars == 1
    assert missing_at not in set(dataset.rows["bar_open_at"])
    assert len(dataset.rows) == 5


def test_dataset_excludes_incomplete_final_minute_book_window() -> None:
    """A partial L2 aggregate must not silently change the feature window."""
    bars, trades, books = _frames(rows=42)
    incomplete_at = books.loc[40, "bar_open_at"]
    books.loc[40, "imbalance_5_delta_60s"] = np.nan

    dataset = build_low_timeframe_dataset(
        bars,
        trades,
        books,
        LowTimeframeDatasetConfig(symbol="BTC"),
    )

    assert dataset.excluded_book_bars == 1
    assert incomplete_at not in set(dataset.rows["bar_open_at"])


def test_dataset_rejects_insufficient_history() -> None:
    """Feature warmup must be complete before a dataset can be scored."""
    bars, trades, books = _frames(rows=36)

    with pytest.raises(ValueError, match="history"):
        build_low_timeframe_dataset(
            bars,
            trades,
            books,
            LowTimeframeDatasetConfig(symbol="BTC"),
        )
