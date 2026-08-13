"""Causal feature tests for HYPE breakout entry attribution."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import pandas as pd
import pytest

from hypervector.research.hype_breakout_entry_features import (
    build_hype_entry_features,
    join_hype_entry_outcomes,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade


def _market(side: str) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=65, freq="1min", tz="UTC")
    close = pd.Series([100.0 + position * 0.1 for position in range(65)], index=index)
    frame = pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": [10.0] * 65,
            "entry_side": [None] * 64 + [side],
            "state_5m": ["BREAKOUT"] * 65,
            "state_1m": ["TREND_UP"] * 65,
            "context_15m": ["TREND_UP"] * 65,
            "structural_direction": [side] * 65,
            "sma_gap_bps": [2.0] * 65,
            "regime_strength_score": [0.6] * 65,
            "bbwp_percentile": [50.0] * 49 + [5.0] + [50.0] * 14 + [99.0],
            "ema_gap_bps_signed": [3.0] * 65,
            "rsi": [60.0] * 65,
            "breakout_volume_ratio": [1.5] * 65,
            "regime_5m_strength_percentile": [72.0] * 65,
            "regime_5m_bbwp_percentile": [34.0] * 65,
            "regime_5m_ema_gap_bps": [8.0] * 65,
            "regime_5m_breakout_volume_ratio": [5.2] * 65,
            "funding_rate": [0.0] * 65,
        },
        index=index,
    )
    return frame


def _trade(
    signal_time: pd.Timestamp,
    side: Literal["long", "short"] = "long",
) -> HypeExitTrade:
    return HypeExitTrade(
        side=side,
        signal_time_utc=signal_time.isoformat(),
        entry_time_utc=(signal_time + pd.Timedelta(minutes=1)).isoformat(),
        exit_time_utc=(signal_time + pd.Timedelta(minutes=2)).isoformat(),
        entry_price=100.0,
        exit_price=101.0,
        stop_price=99.2,
        gross_return_bps=100.0,
        fee_bps=9.0,
        funding_bps=0.0,
        net_return_bps=91.0,
        hold_minutes=1,
        maximum_favorable_excursion_bps=110.0,
        maximum_adverse_excursion_bps=5.0,
        exit_reason="maximum_hold",
    )


def test_features_use_prior_compression_and_directionalize_signal_bar() -> None:
    """The breakout bar cannot leak into the preceding compression window."""
    market = _market("long")

    features = build_hype_entry_features(market)

    row = features.iloc[0]
    assert row["prior_bbwp_min_15m"] == pytest.approx(5.0)
    assert row["current_bbwp_percentile"] == pytest.approx(99.0)
    assert row["directional_bar_body_bps"] > 0.0
    assert row["directional_return_60m_bps"] > 0.0
    assert row["state_1m_alignment"] == 1.0
    assert row["authoritative_5m_strength_percentile"] == pytest.approx(72.0)
    assert row["authoritative_5m_bbwp_percentile"] == pytest.approx(34.0)
    assert row["authoritative_5m_ema_gap_directional_bps"] == pytest.approx(8.0)
    assert row["authoritative_5m_breakout_volume_ratio"] == pytest.approx(5.2)


def test_features_flip_directional_values_for_short_entries() -> None:
    """Identical price action is adverse rather than favorable for a short."""
    features = build_hype_entry_features(_market("short"))

    assert features.iloc[0]["directional_bar_body_bps"] < 0.0
    assert features.iloc[0]["directional_return_60m_bps"] < 0.0
    assert features.iloc[0][
        "authoritative_5m_ema_gap_directional_bps"
    ] == pytest.approx(-8.0)


def test_features_allow_indicator_warmup_only_before_signal_rows() -> None:
    """Unavailable pre-signal indicators cannot invalidate later complete evidence."""
    market = _market("long")
    market.loc[market.index[0], "sma_gap_bps"] = float("nan")
    market.loc[market.index[0], "bbwp_percentile"] = float("nan")

    features = build_hype_entry_features(market)

    assert len(features) == 1
    assert features.iloc[0]["sma_gap_directional_bps"] == pytest.approx(2.0)


def test_outcome_join_requires_exact_signal_side_identity() -> None:
    """A trade cannot inherit features from an opposite-side source event."""
    features = build_hype_entry_features(_market("long"))
    trade = replace(_trade(features.index[0]), side="short")

    with pytest.raises(ValueError, match="side does not match"):
        join_hype_entry_outcomes(features, (trade,))


def test_outcome_join_retains_exact_economic_path_fields() -> None:
    """Attribution rows include costs, excursions, hold time, and outcome."""
    features = build_hype_entry_features(_market("long"))

    rows = join_hype_entry_outcomes(features, (_trade(features.index[0]),))

    assert rows.iloc[0]["gross_return_bps"] == pytest.approx(100.0)
    assert rows.iloc[0]["net_return_bps"] == pytest.approx(91.0)
    assert rows.iloc[0]["maximum_favorable_excursion_bps"] == pytest.approx(110.0)
    assert rows.iloc[0]["exit_reason"] == "maximum_hold"
