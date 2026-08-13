"""Frozen input and timing contract tests for low-timeframe research."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.low_tf_multi_asset_contract import (
    LowTfAssetSpec,
    complete_ohlcv_bars,
    default_low_tf_contract,
    ordered_frame_sha256,
    scored_segment,
)


def _minute_bars(rows: int = 16) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=rows, freq="1min", tz="UTC")
    values = [100.0 + position for position in range(rows)]
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": values,
            "high": [value + 2.0 for value in values],
            "low": [value - 1.0 for value in values],
            "close": [value + 1.0 for value in values],
            "volume": [float(position + 1) for position in range(rows)],
        }
    )


def test_default_contract_freezes_assets_segments_and_shared_risk() -> None:
    contract = default_low_tf_contract()

    assert contract.assets == (
        LowTfAssetSpec("BTC", 40.0),
        LowTfAssetSpec("ETH", 25.0),
        LowTfAssetSpec("SOL", 20.0),
        LowTfAssetSpec("HYPE", 10.0),
    )
    assert contract.execution_minutes == 5
    assert contract.context_minutes == 15
    assert contract.initial_equity_usd == pytest.approx(15_000.0)
    assert contract.leverage == pytest.approx(5.0)
    assert contract.maximum_positions == 2
    assert contract.nominal_round_trip_cost_bps == pytest.approx(13.0)
    assert contract.stress_round_trip_cost_bps == pytest.approx(20.0)
    assert contract.segment("development") == (
        pd.Timestamp("2025-07-28", tz="UTC"),
        pd.Timestamp("2026-01-28", tz="UTC"),
    )
    assert contract.segment("validation") == (
        pd.Timestamp("2026-01-28", tz="UTC"),
        pd.Timestamp("2026-04-28", tz="UTC"),
    )
    assert contract.segment("pseudo_holdout") == (
        pd.Timestamp("2026-04-28", tz="UTC"),
        pd.Timestamp("2026-07-28", tz="UTC"),
    )


def test_complete_ohlcv_bars_aggregates_and_drops_incomplete_bucket() -> None:
    result = complete_ohlcv_bars(_minute_bars(), source_minutes=1, bar_minutes=5)

    assert result["bar_open_at"].tolist() == list(
        pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC")
    )
    assert result["open"].tolist() == [100.0, 105.0, 110.0]
    assert result["high"].tolist() == [106.0, 111.0, 116.0]
    assert result["low"].tolist() == [99.0, 104.0, 109.0]
    assert result["close"].tolist() == [105.0, 110.0, 115.0]
    assert result["volume"].tolist() == [15.0, 40.0, 65.0]


def test_complete_ohlcv_bars_drops_bucket_with_missing_constituent() -> None:
    bars = _minute_bars(10).drop(index=2).reset_index(drop=True)

    result = complete_ohlcv_bars(bars, source_minutes=1, bar_minutes=5)

    assert result["bar_open_at"].tolist() == [
        pd.Timestamp("2026-01-01 00:05", tz="UTC")
    ]


def test_completed_aggregation_is_append_invariant() -> None:
    prefix = _minute_bars(15)
    future = _minute_bars(16).iloc[[15]]

    before = complete_ohlcv_bars(prefix, source_minutes=1, bar_minutes=15)
    after = complete_ohlcv_bars(
        pd.concat([prefix, future], ignore_index=True),
        source_minutes=1,
        bar_minutes=15,
    )

    pd.testing.assert_frame_equal(
        before, after.iloc[: len(before)].reset_index(drop=True)
    )


def test_scored_segment_excludes_warmup_and_end_boundary() -> None:
    bars = pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2025-07-27 23:55", periods=4, freq="5min", tz="UTC"
            ),
            "close": [1.0, 2.0, 3.0, 4.0],
        }
    )

    result = scored_segment(
        bars,
        start=pd.Timestamp("2025-07-28", tz="UTC"),
        end=pd.Timestamp("2025-07-28 00:10", tz="UTC"),
    )

    assert result["bar_open_at"].tolist() == [
        pd.Timestamp("2025-07-28 00:00", tz="UTC"),
        pd.Timestamp("2025-07-28 00:05", tz="UTC"),
    ]


def test_frame_identity_changes_with_values_and_rejects_unordered_input() -> None:
    bars = _minute_bars(5)
    first = ordered_frame_sha256(bars, time_column="timestamp")
    changed = bars.copy()
    changed.loc[0, "close"] += 0.5

    assert ordered_frame_sha256(changed, time_column="timestamp") != first
    with pytest.raises(ValueError, match="ordered and unique"):
        ordered_frame_sha256(bars.iloc[::-1], time_column="timestamp")


@pytest.mark.parametrize("bar_minutes", [0, 6, 10])
def test_aggregation_rejects_incoherent_durations(bar_minutes: int) -> None:
    with pytest.raises(ValueError, match="positive multiple"):
        complete_ohlcv_bars(_minute_bars(), source_minutes=4, bar_minutes=bar_minutes)
