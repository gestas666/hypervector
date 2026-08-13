"""Venue-native signal and mark-risk path tests for MU HIP-3 research."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.hip3_venue_path_bars import build_hip3_venue_path_bars


def _midpoint(symbol: str = "xyz:MU") -> Hip3MidpointBars:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="5min")
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.0,
            "entry_bid": 99.9,
            "entry_ask": 100.1,
            "first_boundary_delay_ms": 0.0,
            "gap_before_bars": 0,
        },
        index=index,
    )
    return Hip3MidpointBars(
        symbol, index[0], index[-1] + pd.Timedelta(minutes=5), 1, 10, 4, 0, bars
    )


def _prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for position, timestamp in enumerate(index):
        for offset in (1_000, 4_000):
            rows.append(
                {
                    "ts_ms": int(timestamp.timestamp() * 1_000) + offset,
                    "mark_price": 100.0 + position,
                }
            )
    return pd.DataFrame(rows)


def _dense_prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for position, timestamp in enumerate(index):
        for offset in range(0, 300_000, 5_000):
            rows.append(
                {
                    "ts_ms": int(timestamp.timestamp() * 1_000) + offset,
                    "mark_price": 100.0 + position,
                }
            )
    return pd.DataFrame(rows)


def _one_trade_per_bar(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_id": [f"t{position}" for position in range(len(index))],
            "ts_exchange_ms": [
                int(timestamp.timestamp() * 1_000) + 1_000 for timestamp in index
            ],
            "price": [100.0 + position for position in range(len(index))],
            "size": 1.0,
        }
    )


def test_mark_boundary_diagnostics_are_epoch_unit_stable() -> None:
    midpoint = _midpoint()
    result = build_hip3_venue_path_bars(
        midpoint,
        _one_trade_per_bar(midpoint.bars.index),
        _dense_prices(midpoint.bars.index),
        bar_minutes=5,
        trade_bundle_complete=True,
    )

    bars = result.bars
    assert bars["first_mark_boundary_delay_ms"].eq(0.0).all()
    assert bars["end_mark_boundary_age_ms"].eq(5_000.0).all()
    assert bars["maximum_mark_interval_ms"].eq(5_000.0).all()
    assert bars["mark_path_complete"].all()


def test_exact_cl_uses_same_hip3_venue_path_contract() -> None:
    midpoint = _midpoint("xyz:CL")

    result = build_hip3_venue_path_bars(
        midpoint,
        _one_trade_per_bar(midpoint.bars.index),
        _dense_prices(midpoint.bars.index),
        bar_minutes=5,
        trade_bundle_complete=True,
    )

    assert result.bars["signal_ohlc_source"].eq("0xarchive_public_trade_ohlc_v1").all()
    assert (
        result.bars["risk_path_source"]
        .eq("0xarchive_mark_price_with_public_trade_context_v1")
        .all()
    )
    assert result.bars["mark_path_complete"].all()


def test_entry_risk_excludes_mark_extrema_before_first_executable_quote() -> None:
    midpoint = _midpoint()
    index = midpoint.bars.index
    midpoint.bars.loc[index[1], "first_boundary_delay_ms"] = 10_000.0
    prices = _dense_prices(index)
    before_entry = int(index[1].timestamp() * 1_000) + 1_000
    prices.loc[len(prices)] = {"ts_ms": before_entry, "mark_price": 1.0}

    result = build_hip3_venue_path_bars(
        midpoint,
        _one_trade_per_bar(index),
        prices,
        bar_minutes=5,
        trade_bundle_complete=True,
    )

    assert result.bars.loc[index[1], "risk_low"] == 1.0
    assert result.bars.loc[index[1], "risk_entry_low"] == 101.0
    assert bool(result.bars.loc[index[1], "entry_mark_path_complete"])


def test_trade_ohlc_is_signal_source_and_zero_trade_bar_resets_state() -> None:
    midpoint = _midpoint()
    index = midpoint.bars.index
    trades = pd.DataFrame(
        {
            "trade_id": ["a", "b", "c", "d"],
            "ts_exchange_ms": [
                int(index[0].timestamp() * 1_000) + 1_000,
                int(index[0].timestamp() * 1_000) + 2_000,
                int(index[2].timestamp() * 1_000) + 1_000,
                int(index[3].timestamp() * 1_000) + 1_000,
            ],
            "price": [101.0, 102.0, 99.0, 98.0],
            "size": [1.0, 2.0, 3.0, 4.0],
        }
    )

    result = build_hip3_venue_path_bars(
        midpoint,
        trades,
        _prices(index),
        bar_minutes=5,
        trade_bundle_complete=True,
    )

    bars = result.bars
    assert bars.loc[index[0], "signal_open"] == 101.0
    assert bars.loc[index[0], "signal_high"] == 102.0
    assert bars.loc[index[0], "signal_close"] == 102.0
    assert bars.loc[index[0], "signal_volume"] == 3.0
    assert bars.loc[index[1], "signal_close"] == 102.0
    assert bool(bars.loc[index[1], "signal_ohlc_synthetic_no_trade"])
    assert bars.loc[index[1], "signal_gap_before_bars"] == 1
    assert bars.loc[index[2], "signal_gap_before_bars"] == 1


def test_leading_zero_trade_bar_is_rejected_without_future_backfill() -> None:
    midpoint = _midpoint()
    index = midpoint.bars.index
    trades = pd.DataFrame(
        {
            "trade_id": ["a"],
            "ts_exchange_ms": [int(index[1].timestamp() * 1_000) + 1_000],
            "price": [101.0],
            "size": [1.0],
        }
    )

    with pytest.raises(ValueError, match="leading zero-trade"):
        build_hip3_venue_path_bars(
            midpoint,
            trades,
            _prices(index),
            bar_minutes=5,
            trade_bundle_complete=True,
        )


def test_same_millisecond_trade_ohlc_is_ordered_by_immutable_trade_id() -> None:
    midpoint = _midpoint()
    index = midpoint.bars.index
    timestamp = int(index[0].timestamp() * 1_000) + 1_000
    rows = [
        {"trade_id": "b", "ts_exchange_ms": timestamp, "price": 102.0, "size": 1.0},
        {"trade_id": "a", "ts_exchange_ms": timestamp, "price": 101.0, "size": 1.0},
    ]
    for position, bar in enumerate(index[1:], start=1):
        rows.append(
            {
                "trade_id": f"z{position}",
                "ts_exchange_ms": int(bar.timestamp() * 1_000) + 1_000,
                "price": 102.0 + position,
                "size": 1.0,
            }
        )

    first = build_hip3_venue_path_bars(
        midpoint,
        pd.DataFrame(rows),
        _prices(index),
        bar_minutes=5,
        trade_bundle_complete=True,
    )
    second = build_hip3_venue_path_bars(
        midpoint,
        pd.DataFrame(list(reversed(rows))),
        _prices(index),
        bar_minutes=5,
        trade_bundle_complete=True,
    )

    assert first.bars.loc[index[0], "signal_open"] == 101.0
    assert first.bars.loc[index[0], "signal_close"] == 102.0
    pd.testing.assert_series_equal(
        first.bars["signal_close"], second.bars["signal_close"]
    )
