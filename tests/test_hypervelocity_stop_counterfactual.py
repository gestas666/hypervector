"""Causal consolidation-wick stop counterfactual tests."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from hypervector.research.hypervelocity_candidate_eval import CandidateBarrierConfig
from hypervector.research.hypervelocity_stop_counterfactual import (
    attach_consolidation_wick_stops,
    confirmed_pivot_stop_events,
    evaluate_confirmed_pivot_stops,
    evaluate_consolidation_wick_stops,
    evaluate_fixed_margin_stops,
    evaluate_liquidation_proximity_stops,
    last_bbwp_consolidation_bounds,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=8, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * 8,
            "high": [101.0, 102.0, 100.5, 100.5, 100.5, 100.5, 100.5, 100.5],
            "low": [99.5, 99.0, 99.8, 99.8, 98.9, 99.8, 99.8, 99.8],
            "close": [100.0] * 8,
            "volume": [1.0] * 8,
        },
        index=index,
    )


def test_last_compression_bounds_freeze_only_after_episode_ends() -> None:
    bars = _bars()
    bbwp = pd.Series([20.0, 10.0, 30.0, 30.0, 20.0, 30.0, 30.0, 30.0], index=bars.index)

    result = last_bbwp_consolidation_bounds(bars, bbwp, threshold=25.0)

    assert result.iloc[:2].isna().all().all()
    assert result["long_stop"].iloc[2:4].tolist() == [99.0, 99.0]
    assert result["short_stop"].iloc[2:4].tolist() == [102.0, 102.0]
    assert result["long_stop"].iloc[5:].tolist() == [98.9, 98.9, 98.9]


def test_consolidation_bounds_are_prefix_stable() -> None:
    bars = _bars()
    bbwp = pd.Series([20.0, 10.0, 30.0, 30.0, 20.0, 30.0, 30.0, 30.0], index=bars.index)

    prefix = last_bbwp_consolidation_bounds(
        bars.iloc[:5], bbwp.iloc[:5], threshold=25.0
    )
    full = last_bbwp_consolidation_bounds(bars, bbwp, threshold=25.0)

    pd.testing.assert_frame_equal(prefix, full.iloc[:5])


def test_attach_consolidation_wicks_selects_directional_frozen_level() -> None:
    bars = _bars()
    decisions = pd.DataFrame(
        {
            "bbwp_percentile": [20.0, 10.0, 30.0, 30.0, 20.0, 30.0, 30.0, 30.0],
            "entry_direction": [None, None, "long", "short", None, "long", None, None],
        },
        index=bars.index,
    )

    result = attach_consolidation_wick_stops(bars, decisions, threshold=25.0)

    assert result.loc[bars.index[2], "entry_stop_price"] == 99.0
    assert result.loc[bars.index[3], "entry_stop_price"] == 102.0
    assert result.loc[bars.index[5], "entry_stop_price"] == 98.9
    assert pd.isna(result.loc[bars.index[4], "entry_stop_price"])


def test_wick_stop_reports_target_regret_on_exact_filled_lifecycle() -> None:
    bars = _bars()
    decisions = pd.DataFrame(
        {"bbwp_percentile": [20.0, 10.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0]},
        index=bars.index,
    )
    lifecycles = pd.DataFrame(
        {
            "direction": ["long"],
            "signal_time_utc": ["2026-01-01T00:03:00Z"],
            "entry_time_utc": ["2026-01-01T00:03:10Z"],
            "outcome_time_utc": ["2026-01-01T00:06:10Z"],
            "status": ["target_completed"],
            "entry_price": [100.0],
            "quantity": [1.0],
            "net_pnl": [0.17],
        }
    )

    report = evaluate_consolidation_wick_stops(bars, decisions, lifecycles)

    assert report.filled_lifecycles == 1
    assert report.effective_stops == 1
    assert report.stop_hits == 1
    assert report.target_stop_regret == 1
    assert report.liquidations_avoided == 0
    assert report.counterfactual_net_pnl_usd < report.original_net_pnl_usd
    json.dumps(report.to_dict(), allow_nan=False)


def test_wick_stop_prefers_measured_liquidation_boundary() -> None:
    """Current-lead screens must not recompute the legacy 40x boundary."""
    bars = _bars()
    decisions = pd.DataFrame(
        {"bbwp_percentile": [20.0, 10.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0]},
        index=bars.index,
    )
    lifecycles = pd.DataFrame(
        {
            "direction": ["long"],
            "signal_time_utc": ["2026-01-01T00:03:00Z"],
            "entry_time_utc": ["2026-01-01T00:03:10Z"],
            "outcome_time_utc": ["2026-01-01T00:06:10Z"],
            "status": ["liquidated"],
            "entry_price": [100.0],
            "quantity": [1.0],
            "liquidation_price": [99.5],
            "net_pnl": [-1.0],
        }
    )
    config = CandidateBarrierConfig(
        initial_equity=15_000.0,
        margin_fraction=0.50,
        leverage=30.0,
    )

    report = evaluate_consolidation_wick_stops(
        bars,
        decisions,
        lifecycles,
        config=config,
    )

    assert report.ineffective_stops == 1
    assert report.effective_stops == 0
    assert report.liquidations_avoided == 0


def test_wick_stop_retains_time_exited_lifecycle() -> None:
    """A resolved maximum-hold trade must not disappear from the screen."""
    bars = _bars()
    decisions = pd.DataFrame(
        {"bbwp_percentile": [20.0, 10.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0]},
        index=bars.index,
    )
    lifecycles = pd.DataFrame(
        {
            "direction": ["long"],
            "signal_time_utc": ["2026-01-01T00:03:00Z"],
            "entry_time_utc": ["2026-01-01T00:03:10Z"],
            "outcome_time_utc": ["2026-01-01T00:06:10Z"],
            "status": ["time_exited"],
            "entry_price": [100.0],
            "quantity": [1.0],
            "liquidation_price": [98.0],
            "net_pnl": [-0.1],
        }
    )

    report = evaluate_consolidation_wick_stops(bars, decisions, lifecycles)

    assert report.filled_lifecycles == 1
    assert report.trades[0].status == "time_exited"


def test_liquidation_proximity_stop_is_frozen_between_entry_and_boundary() -> None:
    bars = _bars()
    bars.loc[bars.index[4], "low"] = 98.5
    lifecycles = pd.DataFrame(
        {
            "direction": ["long"],
            "signal_time_utc": ["2026-01-01T00:03:00Z"],
            "entry_time_utc": ["2026-01-01T00:03:10Z"],
            "outcome_time_utc": ["2026-01-01T00:06:10Z"],
            "status": ["liquidated"],
            "entry_price": [100.0],
            "quantity": [1.0],
            "net_pnl": [-1.7],
        }
    )

    report = evaluate_liquidation_proximity_stops(
        bars,
        lifecycles,
        distance_fraction=0.5,
    )

    trade = report.trades[0]
    assert trade.entry_price > trade.stop_price > trade.liquidation_price
    assert report.stop_hits == 1
    assert report.liquidations_avoided == 1
    assert report.target_stop_regret == 0


def test_liquidation_proximity_rejects_boundary_fraction() -> None:
    bars = _bars()
    lifecycles = pd.DataFrame()

    with pytest.raises(ValueError, match="distance_fraction"):
        evaluate_liquidation_proximity_stops(
            bars,
            lifecycles,
            distance_fraction=1.0,
        )


def test_fixed_margin_stop_converts_margin_percent_to_price_distance() -> None:
    bars = _bars()
    lifecycles = pd.DataFrame(
        {
            "direction": ["long"],
            "signal_time_utc": ["2026-01-01T00:03:00Z"],
            "entry_time_utc": ["2026-01-01T00:03:10Z"],
            "outcome_time_utc": ["2026-01-01T00:06:10Z"],
            "status": ["liquidated"],
            "entry_price": [100.0],
            "quantity": [1.0],
            "net_pnl": [-1.7],
        }
    )

    report = evaluate_fixed_margin_stops(
        bars,
        lifecycles,
        margin_stop_pct=8.0,
    )

    assert report.trades[0].stop_price == pytest.approx(99.8)
    assert report.liquidations_avoided == 1


def test_fixed_margin_stop_rejects_invalid_percent() -> None:
    with pytest.raises(ValueError, match="margin_stop_pct"):
        evaluate_fixed_margin_stops(
            _bars(),
            pd.DataFrame(),
            margin_stop_pct=0.0,
        )


def _pivot_bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=8, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * 8,
            "high": [100.0, 100.5, 101.0, 100.5, 100.0, 100.5, 101.5, 101.0],
            "low": [100.0, 99.5, 99.0, 99.5, 100.0, 99.5, 98.5, 99.0],
            "close": [100.0] * 8,
        },
        index=index,
    )


def test_confirmed_pivot_stops_publish_only_after_right_bars_close() -> None:
    bars = _pivot_bars()

    events = confirmed_pivot_stop_events(
        bars,
        left_bars=2,
        right_bars=2,
        buffer_bps=10.0,
    )
    prefix = confirmed_pivot_stop_events(
        bars.iloc[:5],
        left_bars=2,
        right_bars=2,
        buffer_bps=10.0,
    )

    expected_time = bars.index[5]
    assert events.index[0] == expected_time
    assert events.loc[expected_time, "long_stop"] == pytest.approx(98.901)
    assert events.loc[expected_time, "short_stop"] == pytest.approx(101.101)
    pd.testing.assert_frame_equal(prefix, events.loc[:expected_time])


def test_confirmed_pivot_stop_uses_latest_causally_available_level() -> None:
    bars = _pivot_bars()
    lifecycles = pd.DataFrame(
        {
            "direction": ["long"],
            "signal_time_utc": ["2026-01-01T00:05:00Z"],
            "entry_time_utc": ["2026-01-01T00:05:10Z"],
            "outcome_time_utc": ["2026-01-01T00:07:10Z"],
            "status": ["liquidated"],
            "entry_price": [100.0],
            "quantity": [1.0],
            "net_pnl": [-1.0],
        }
    )

    report = evaluate_confirmed_pivot_stops(
        bars,
        lifecycles,
        left_bars=2,
        right_bars=2,
    )

    assert report.trades[0].stop_price == 99.0
    assert report.stop_hits == 1
    assert report.liquidations_avoided == 1
