"""Completed-candle capture diagnostics for accepted cohort trades."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_trade_capture import build_completed_hold_capture
from hypervector.research.cohort_trade_reflection_index import Candle

_MINUTE_MS = 60_000


def test_long_capture_uses_only_candles_completed_before_exit() -> None:
    """MFE and giveback exclude the still-forming exit-minute candle."""
    candles = {
        _MINUTE_MS: Candle(_MINUTE_MS, 100.0, 105.0, 99.0, 104.0),
        2 * _MINUTE_MS: Candle(2 * _MINUTE_MS, 102.5, 103.0, 101.0, 102.0),
        3 * _MINUTE_MS: Candle(3 * _MINUTE_MS, 102.0, 110.0, 90.0, 100.0),
    }

    result = build_completed_hold_capture(
        candles,
        side="long",
        entry={"venue_timestamp_ms": 30_000, "price": 100.0},
        exit_leg={"venue_timestamp_ms": 3 * _MINUTE_MS + 30_000, "price": 103.0},
    )

    assert result["status"] == "resolved"
    assert result["completed_bars"] == 2
    assert result["maximum_favorable_excursion_bps"] == pytest.approx(500.0)
    assert result["maximum_adverse_excursion_bps"] == pytest.approx(100.0)
    assert result["realized_gross_return_bps"] == pytest.approx(300.0)
    assert result["gross_mfe_capture_ratio"] == pytest.approx(0.6)
    assert result["peak_giveback_bps"] == pytest.approx(200.0)


def test_missing_completed_candle_is_not_silently_skipped() -> None:
    """A hole in the holding path remains an explicit technical gap."""
    candles = {
        _MINUTE_MS: Candle(_MINUTE_MS, 100.0, 101.0, 99.0, 100.0),
        3 * _MINUTE_MS: Candle(3 * _MINUTE_MS, 102.0, 103.0, 101.0, 102.0),
    }

    result = build_completed_hold_capture(
        candles,
        side="short",
        entry={"venue_timestamp_ms": 30_000, "price": 100.0},
        exit_leg={"venue_timestamp_ms": 4 * _MINUTE_MS + 1, "price": 99.0},
    )

    assert result == {
        "status": "missing_data",
        "completed_bars_expected": 3,
        "completed_bars_observed": 2,
        "missing_candle_count": 1,
    }


def test_losing_trade_that_never_cleared_cost_hurdle_is_distinct() -> None:
    """A small gross move should not be mislabeled as an exit-giveback loss."""
    candles = {
        _MINUTE_MS: Candle(_MINUTE_MS, 100.0, 100.08, 99.99, 100.05),
    }

    result = build_completed_hold_capture(
        candles,
        side="long",
        entry={"venue_timestamp_ms": 30_000, "price": 100.0, "size": 1.0},
        exit_leg={"venue_timestamp_ms": 2 * _MINUTE_MS + 1, "price": 100.05},
        economics={"fees_usd": 0.09, "funding_usd": -0.01, "net_pnl_usd": -0.05},
    )

    assert result["observed_cost_hurdle_bps"] == pytest.approx(10.0)
    assert result["maximum_net_excursion_bps"] == pytest.approx(-2.0)
    assert result["realized_net_return_bps"] == pytest.approx(-5.0)
    assert result["economic_outcome"] == "never_cleared_observed_cost_hurdle"
    assert result["maximum_net_excursion_executable"] is False
    assert result["economic_hurdle_basis"] == (
        "actual_fees_and_funding_over_filled_entry_notional"
    )


def test_losing_trade_that_cleared_cost_hurdle_is_exit_giveback() -> None:
    """A profitable intratrade excursion followed by a loss is separately named."""
    candles = {
        _MINUTE_MS: Candle(_MINUTE_MS, 100.0, 100.50, 99.99, 100.05),
    }

    result = build_completed_hold_capture(
        candles,
        side="long",
        entry={"venue_timestamp_ms": 30_000, "price": 100.0, "size": 1.0},
        exit_leg={"venue_timestamp_ms": 2 * _MINUTE_MS + 1, "price": 100.05},
        economics={"fees_usd": 0.09, "funding_usd": -0.01, "net_pnl_usd": -0.05},
    )

    assert result["maximum_net_excursion_bps"] == pytest.approx(40.0)
    assert result["economic_outcome"] == "cleared_cost_hurdle_then_surrendered"
