"""Causal contracts for the bounded RSI and absorption challengers."""

from __future__ import annotations

from importlib import import_module

import pandas as pd
import pytest


def _challengers() -> object:
    """Import the desired feature module or fail as a TDD assertion."""
    try:
        return import_module("hypervector.research.low_tf_bounded_challengers")
    except ModuleNotFoundError:
        pytest.fail("bounded challenger module is not implemented")


def test_three_drive_signal_uses_confirmed_pivot_stop_and_next_bar_entry() -> None:
    module = _challengers()
    times = pd.date_range("2026-01-01", periods=13, freq="5min", tz="UTC")
    highs = [1, 2, 10, 2, 1, 2, 12, 2, 1, 2, 14, 2, 1]
    frame = pd.DataFrame(
        {
            "bar_open_at": times,
            "high": highs,
            "low": [value - 1 for value in highs],
            "close": [9.0] * 12 + [13.0],
            "rsi": [50, 55, 75, 55, 50, 55, 70, 55, 50, 55, 65, 55, 50],
            "ema_fast_5m": [11.0] * 13,
        }
    )

    signals = module.build_three_drive_signals(frame, symbol="ETH")

    assert len(signals) == 1
    signal = signals.iloc[0]
    assert signal["family"] == "three_drive_rsi_reversal_v1"
    assert signal["side"] == "short"
    assert (
        signal["decision_time_utc"] == (times[-1] + pd.Timedelta(minutes=5)).isoformat()
    )
    assert signal["stop_anchor_price"] == 14.0
    assert signal["target_anchor_price"] == 11.0
    assert signal["execution_authority"] == "none"


def test_three_drive_signal_is_symmetric_for_confirmed_bullish_troughs() -> None:
    module = _challengers()
    times = pd.date_range("2026-01-01", periods=13, freq="5min", tz="UTC")
    lows = [10, 9, 3, 9, 10, 9, 2, 9, 10, 9, 1, 9, 10]
    frame = pd.DataFrame(
        {
            "bar_open_at": times,
            "high": [value + 1 for value in lows],
            "low": lows,
            "close": [3.0] * 12 + [2.0],
            "rsi": [50, 45, 20, 45, 50, 45, 25, 45, 50, 45, 28, 45, 50],
            "ema_fast_5m": [4.0] * 13,
        }
    )

    signals = module.build_three_drive_signals(frame, symbol="SOL")

    assert len(signals) == 1
    signal = signals.iloc[0]
    assert signal["side"] == "long"
    assert signal["stop_anchor_price"] == 1.0
    assert signal["target_anchor_price"] == 4.0


def test_three_drive_signal_accepts_only_leading_rsi_warmup_gaps() -> None:
    module = _challengers()
    times = pd.date_range("2026-01-01", periods=15, freq="5min", tz="UTC")
    highs = [1, 1, 1, 2, 10, 2, 1, 2, 12, 2, 1, 2, 14, 2, 1]
    frame = pd.DataFrame(
        {
            "bar_open_at": times,
            "high": highs,
            "low": [value - 1 for value in highs],
            "close": [9.0] * 14 + [13.0],
            "rsi": [
                float("nan"),
                float("nan"),
                50,
                55,
                75,
                55,
                50,
                55,
                70,
                55,
                50,
                55,
                65,
                55,
                50,
            ],
            "ema_fast_5m": [11.0] * 15,
        }
    )

    signals = module.build_three_drive_signals(frame, symbol="ETH")

    assert len(signals) == 1
    assert (
        signals.iloc[0]["decision_time_utc"]
        == (times[-1] + pd.Timedelta(minutes=5)).isoformat()
    )


def test_absorption_long_requires_price_low_and_opposing_bid_pressure() -> None:
    module = _challengers()
    times = pd.date_range("2026-01-01", periods=13, freq="5min", tz="UTC")
    frame = pd.DataFrame(
        {
            "bar_open_at": times,
            "high": [102.0] * 12 + [101.0],
            "low": [99.0] * 12 + [90.0],
            "close": [100.0] * 12 + [91.0],
            "return_1_bps": [0.0] * 12 + [-900.0],
            "trade_flow_imbalance": [0.0] * 12 + [-0.60],
            "imbalance_5_last": [0.0] * 12 + [0.30],
            "imbalance_5_delta_60s": [0.0] * 12 + [0.40],
            "spread_bps_last": [2.0] * 12 + [1.0],
            "micro_price_delta_bps": [0.0] * 12 + [0.20],
        }
    )

    signals = module.build_absorption_signals(frame, symbol="SOL")

    assert len(signals) == 1
    signal = signals.iloc[0]
    assert signal["family"] == "l2_absorption_reversal_v1"
    assert signal["side"] == "long"
    assert signal["stop_anchor_price"] == 90.0
    assert signal["target_anchor_price"] == pytest.approx(91.0 * 1.0025)
    assert (
        signal["decision_time_utc"] == (times[-1] + pd.Timedelta(minutes=5)).isoformat()
    )


def test_absorption_short_is_the_exact_symmetric_pressure_contract() -> None:
    module = _challengers()
    times = pd.date_range("2026-01-01", periods=13, freq="5min", tz="UTC")
    frame = pd.DataFrame(
        {
            "bar_open_at": times,
            "high": [101.0] * 12 + [110.0],
            "low": [98.0] * 12 + [99.0],
            "close": [100.0] * 12 + [109.0],
            "return_1_bps": [0.0] * 12 + [900.0],
            "trade_flow_imbalance": [0.0] * 12 + [0.60],
            "imbalance_5_last": [0.0] * 12 + [-0.30],
            "imbalance_5_delta_60s": [0.0] * 12 + [-0.40],
            "spread_bps_last": [2.0] * 12 + [1.0],
            "micro_price_delta_bps": [0.0] * 12 + [-0.20],
        }
    )

    signals = module.build_absorption_signals(frame, symbol="SOL")

    assert len(signals) == 1
    signal = signals.iloc[0]
    assert signal["side"] == "short"
    assert signal["stop_anchor_price"] == 110.0
    assert signal["target_anchor_price"] == pytest.approx(109.0 * 0.9975)
