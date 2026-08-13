"""Source-parity tests for the historical HYPE exit-replay market."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hype_breakout_exit_market import (
    assemble_hype_exit_market,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0] * 5,
            "volume": [10.0] * 5,
        },
        index=index,
    )


def test_assembly_emits_only_directional_breakout_transitions() -> None:
    """Persistent breakout minutes cannot become repeated historical entries."""
    bars = _bars()
    signals = pd.DataFrame(
        {"structural_direction": ["long", "long", "long", "neutral", "short"]},
        index=bars.index,
    )
    regimes = pd.DataFrame(
        {"state_5m": ["RANGE", "BREAKOUT", "BREAKOUT", "RANGE", "BREAKOUT"]},
        index=bars.index,
    )
    funding = pd.DataFrame({"timestamp": [bars.index[1]], "funding_rate": [0.001]})

    market, evidence = assemble_hype_exit_market(bars, signals, regimes, funding)

    assert market["entry_side"].tolist() == [None, "long", None, None, "short"]
    assert market["funding_rate"].tolist() == [0.0, 0.001, 0.0, 0.0, 0.0]
    assert evidence.directional_entry_signals == 2
    assert evidence.funding_events_matched == 1


def test_assembly_can_follow_the_actual_breakout_direction() -> None:
    """The challenger uses the completed 5m breakout side, not the SMA side."""
    bars = _bars()
    signals = pd.DataFrame(
        {"structural_direction": ["long", "long", "long", "short", "short"]},
        index=bars.index,
    )
    regimes = pd.DataFrame(
        {
            "state_5m": ["RANGE", "BREAKOUT", "BREAKOUT", "RANGE", "BREAKOUT"],
            "structural_direction": [
                None,
                "short",
                "short",
                None,
                "long",
            ],
        },
        index=bars.index,
    )

    market, evidence = assemble_hype_exit_market(
        bars,
        signals,
        regimes,
        pd.DataFrame(),
        entry_direction_mode="breakout",
    )

    assert market["entry_side"].tolist() == [None, "short", None, None, "long"]
    assert market["breakout_side"].iloc[[1, 2, 4]].tolist() == [
        "short",
        "short",
        "long",
    ]
    assert market["breakout_side"].iloc[[0, 3]].isna().all()
    assert evidence.directional_entry_signals == 2


def test_assembly_retains_causal_entry_feature_sources() -> None:
    """The reconstructed market preserves only signal-time feature evidence."""
    bars = _bars()
    signals = pd.DataFrame(
        {
            "structural_direction": ["long"] * 5,
            "sma_gap_bps": [1.0, 2.0, 3.0, 4.0, 5.0],
        },
        index=bars.index,
    )
    regimes = pd.DataFrame(
        {
            "state_5m": ["RANGE", "BREAKOUT", "BREAKOUT", "RANGE", "BREAKOUT"],
            "state_1m": ["RANGE"] * 5,
            "context_15m": ["TREND_UP"] * 5,
            "regime_strength_score": [0.1, 0.2, 0.3, 0.4, 0.5],
            "bbwp_percentile": [10.0, 20.0, 30.0, 40.0, 50.0],
            "ema_gap_bps_signed": [1.0] * 5,
            "rsi": [55.0] * 5,
            "breakout_volume_ratio": [1.5] * 5,
            "regime_5m_strength_percentile": [61.0] * 5,
            "regime_5m_bbwp_percentile": [32.0] * 5,
            "regime_5m_ema_gap_bps": [7.0] * 5,
            "regime_5m_breakout_volume_ratio": [3.0] * 5,
            "regime_5m_rsi": [44.0, 45.0, 46.0, 47.0, 48.0],
            "regime_5m_rsi_ema": [49.0] * 5,
        },
        index=bars.index,
    )

    market, _ = assemble_hype_exit_market(bars, signals, regimes, pd.DataFrame())

    assert market["sma_gap_bps"].tolist() == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert market["bbwp_percentile"].tolist() == [10.0, 20.0, 30.0, 40.0, 50.0]
    assert market["context_15m"].tolist() == ["TREND_UP"] * 5
    assert market["regime_5m_breakout_volume_ratio"].tolist() == [3.0] * 5
    assert market["regime_5m_rsi"].tolist() == [44.0, 45.0, 46.0, 47.0, 48.0]
    assert market["regime_5m_rsi_ema"].tolist() == [49.0] * 5


def test_assembly_rejects_misaligned_live_source_frames() -> None:
    """Historical analysis cannot silently shift regimes away from live bars."""
    bars = _bars()
    signals = pd.DataFrame(
        {"structural_direction": ["long"] * 4}, index=bars.index[:-1]
    )
    regimes = pd.DataFrame({"state_5m": ["RANGE"] * 5}, index=bars.index)

    with pytest.raises(ValueError, match="share one index"):
        assemble_hype_exit_market(bars, signals, regimes, pd.DataFrame())


def test_assembly_rejects_duplicate_funding_boundaries() -> None:
    """One hourly funding settlement may be applied at most once."""
    bars = _bars()
    signals = pd.DataFrame({"structural_direction": ["long"] * 5}, index=bars.index)
    regimes = pd.DataFrame({"state_5m": ["RANGE"] * 5}, index=bars.index)
    funding = pd.DataFrame(
        {
            "timestamp": [bars.index[1], bars.index[1]],
            "funding_rate": [0.001, 0.001],
        }
    )

    with pytest.raises(ValueError, match="funding timestamps must be unique"):
        assemble_hype_exit_market(bars, signals, regimes, funding)
