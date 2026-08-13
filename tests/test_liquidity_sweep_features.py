"""Causality tests for five-minute sweep features and event arms."""

from __future__ import annotations

import pandas as pd

from hypervector.research.liquidity_sweep_contract import LiquiditySweepConfig
from hypervector.research.liquidity_sweep_features import (
    build_liquidity_sweep_events,
)


def _feature_rows() -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=15, freq="5min", tz="UTC")
    rows = pd.DataFrame(
        {
            "bar_open_at": times,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 10.0,
            "buy_volume": 6.0,
            "sell_volume": 4.0,
            "imbalance_5_last": 0.2,
            "micro_price_delta_bps": 0.4,
            "spread_bps_last": 1.0,
            "context_15m": "RANGE",
            "segment_id": 1,
        }
    )
    return rows


def test_reclaim_and_acceptance_emit_symmetric_sides() -> None:
    """Completed sweeps map to fixed reversal or continuation directions."""
    rows = _feature_rows()
    rows.loc[12, ["low", "close"]] = [97.0, 100.0]
    rows.loc[13, ["high", "close"]] = [103.0, 102.0]

    events, audit = build_liquidity_sweep_events(
        rows, symbol="BTC", config=LiquiditySweepConfig()
    )

    selected = events.set_index("bar_open_at")
    assert selected.loc[rows.loc[12, "bar_open_at"], "arm"] == (
        "sweep_reclaim_reversal"
    )
    assert selected.loc[rows.loc[12, "bar_open_at"], "side"] == "long"
    assert selected.loc[rows.loc[13, "bar_open_at"], "arm"] == (
        "sweep_acceptance_continuation"
    )
    assert selected.loc[rows.loc[13, "bar_open_at"], "side"] == "long"
    assert audit["dual_sweep_ambiguous"] == 0


def test_dual_sweep_is_audited_and_excluded() -> None:
    """A bar sweeping both structural sides cannot receive a guessed direction."""
    rows = _feature_rows()
    rows.loc[12, ["high", "low", "close"]] = [103.0, 97.0, 100.0]

    events, audit = build_liquidity_sweep_events(
        rows, symbol="SOL", config=LiquiditySweepConfig()
    )

    assert events.empty
    assert audit["dual_sweep_ambiguous"] == 1


def test_structure_window_resets_at_gap_segment() -> None:
    """Prior levels cannot bridge a discontinuity in venue bars."""
    rows = _feature_rows()
    rows.loc[12:, "segment_id"] = 2
    rows.loc[12, ["high", "close"]] = [103.0, 102.0]

    events, audit = build_liquidity_sweep_events(
        rows, symbol="BTC", config=LiquiditySweepConfig()
    )

    assert events.empty
    assert audit["warmup_incomplete"] == 15
