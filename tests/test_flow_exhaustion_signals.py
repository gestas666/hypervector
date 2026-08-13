"""Causal contracts for the five-minute flow-exhaustion signal."""

from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from hypervector.research.flow_exhaustion_signals import (
    FlowExhaustionSignalConfig,
    build_flow_exhaustion_signals,
    build_segmented_flow_exhaustion_signals,
)


def _frame() -> pd.DataFrame:
    opens = pd.date_range("2026-01-01", periods=6, freq="5min", tz=UTC)
    frame = pd.DataFrame(
        {
            "bar_open_at": opens,
            "last_book_at": opens + pd.Timedelta(minutes=5),
            "open": [100.0] * 6,
            "high": [100.11, 100.11, 100.11, 100.11, 100.05, 100.55],
            "low": [99.99, 99.99, 99.99, 99.99, 99.55, 99.95],
            "close": [100.10, 100.10, 100.10, 100.10, 99.60, 100.50],
            "buy_volume": [6.0, 6.0, 6.0, 6.0, 10.0, 95.0],
            "sell_volume": [4.0, 4.0, 4.0, 4.0, 90.0, 5.0],
            "final_60_buy_volume": [5.0, 5.0, 5.0, 5.0, 8.0, 2.0],
            "final_60_sell_volume": [5.0, 5.0, 5.0, 5.0, 2.0, 8.0],
            "imbalance_5_last": [0.0, 0.0, 0.0, 0.0, 0.4, -0.4],
        }
    )
    return frame


def _config() -> FlowExhaustionSignalConfig:
    return FlowExhaustionSignalConfig(lookback_bars=4)


def test_signal_is_symmetric_and_uses_prior_only_thresholds() -> None:
    """Current shocks must not contaminate their own causal percentiles."""
    report = build_flow_exhaustion_signals(_frame(), "BTC", _config())

    assert report.evaluated_bars == 2
    assert report.signals["side"].tolist() == ["long", "short"]
    first = report.signals.iloc[0]
    assert first["shock_threshold_bps"] == pytest.approx(10.0)
    assert first["flow_threshold"] == pytest.approx(0.2)
    assert first["target_price"] == pytest.approx(100.0)
    assert first["stop_price"] == pytest.approx(99.55 * (1.0 - 0.0002))
    assert first["available_at_utc"] == first["bar_open_at"] + pd.Timedelta(minutes=5)


def test_signal_requires_final_flow_and_book_to_oppose_shock() -> None:
    """A price spike alone is not the registered replenishment mechanism."""
    frame = _frame()
    frame.loc[4, "final_60_buy_volume"] = 1.0
    frame.loc[4, "final_60_sell_volume"] = 9.0

    report = build_flow_exhaustion_signals(frame, "BTC", _config())

    assert report.signals["side"].tolist() == ["short"]
    assert report.blockers["final_flow_not_reversed"] == 1


def test_signal_treats_zero_final_minute_flow_as_missing_evidence() -> None:
    """A quiet final minute is a causal blocker rather than malformed input."""
    frame = _frame()
    frame.loc[4, "final_60_buy_volume"] = 0.0
    frame.loc[4, "final_60_sell_volume"] = 0.0

    report = build_flow_exhaustion_signals(frame, "BTC", _config())

    assert report.signals["side"].tolist() == ["short"]
    assert report.blockers["final_flow_unavailable"] == 1


def test_signal_rejects_future_book_observation() -> None:
    """A snapshot after the completed-bar boundary is look-ahead leakage."""
    frame = _frame()
    frame.loc[5, "last_book_at"] += pd.Timedelta(milliseconds=1)

    with pytest.raises(ValueError, match="future book"):
        build_flow_exhaustion_signals(frame, "BTC", _config())


def test_signal_rejects_noncontiguous_five_minute_input() -> None:
    """A rolling threshold must not silently span an unreported data gap."""
    frame = _frame()
    frame.loc[3:, "bar_open_at"] += pd.Timedelta(minutes=5)
    frame.loc[3:, "last_book_at"] += pd.Timedelta(minutes=5)

    with pytest.raises(ValueError, match="five-minute cadence"):
        build_flow_exhaustion_signals(frame, "BTC", _config())


def test_segmented_signal_resets_causal_history_across_data_gap() -> None:
    """Each side of an archive gap must earn an independent warm-up."""
    first = _frame().iloc[:5].copy()
    second = first.copy()
    second["bar_open_at"] += pd.Timedelta(hours=1)
    second["last_book_at"] += pd.Timedelta(hours=1)
    rows = pd.concat([first, second], ignore_index=True)

    report = build_segmented_flow_exhaustion_signals(rows, "BTC", _config())

    assert report.evaluated_bars == 2
    assert report.signals["side"].tolist() == ["long", "long"]
