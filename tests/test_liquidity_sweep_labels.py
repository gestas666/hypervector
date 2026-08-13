"""Pessimistic lifecycle tests for structural sweep barriers."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.liquidity_sweep_contract import LiquiditySweepConfig
from hypervector.research.liquidity_sweep_labels import (
    label_liquidity_sweep_events,
    serialize_liquidity_sweep_outcomes,
)


def _bars(*, ambiguous: bool = False) -> pd.DataFrame:
    highs = [100.5, 102.5, 101.0]
    lows = [99.5, 98.5 if ambiguous else 99.5, 99.0]
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01 01:00", periods=3, freq="5min", tz="UTC"
            ),
            "open": [100.0, 100.5, 100.0],
            "high": highs,
            "low": lows,
            "close": [100.2, 100.0, 99.5],
        }
    )


def _event() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": "BTC:one",
                "symbol": "BTC",
                "bar_open_at": pd.Timestamp("2026-01-01 00:55", tz="UTC"),
                "available_at_utc": pd.Timestamp("2026-01-01 01:00", tz="UTC"),
                "arm": "sweep_reclaim_reversal",
                "side": "long",
                "protective_extreme": 99.0,
                "spread_bps_last": 1.0,
                "context_15m": "RANGE",
            }
        ]
    )


def test_structural_target_and_stop_first_are_pessimistic() -> None:
    """When one bar touches both barriers, the structural stop wins."""
    outcomes = label_liquidity_sweep_events(
        _bars(ambiguous=True),
        _event(),
        pd.DataFrame(columns=["timestamp", "funding_rate"]),
        LiquiditySweepConfig(),
    )
    row = outcomes.iloc[0]

    assert row["status"] == "ambiguous_stop_first"
    assert row["stop_price"] == pytest.approx(98.9901)
    assert row["target_price"] == pytest.approx(102.0798)
    assert row["maximum_adverse_excursion_bps"] > 0.0
    assert row["sampled_mtm_trough_bps"] < 0.0


def test_overlapping_events_are_displaced_per_symbol_and_arm() -> None:
    """A research arm cannot hold two positions in one asset concurrently."""
    events = pd.concat([_event(), _event()], ignore_index=True)
    events.loc[1, "event_id"] = "BTC:two"
    events.loc[1, "available_at_utc"] += pd.Timedelta(minutes=5)
    outcomes = label_liquidity_sweep_events(
        _bars(),
        events,
        pd.DataFrame(columns=["timestamp", "funding_rate"]),
        LiquiditySweepConfig(maximum_hold_bars=2),
    )

    serialized = serialize_liquidity_sweep_outcomes(outcomes)

    assert serialized["accepted"].tolist() == [True, False]
    assert serialized.iloc[1]["displacement_reason"] == "symbol_position_open"
