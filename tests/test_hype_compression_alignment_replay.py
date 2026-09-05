"""Tests for the causal HYPE compression-alignment replay."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_compression_alignment_replay import (
    build_hype_compression_alignment_markets,
    build_hype_compression_alignment_replay,
)


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=160, freq="1min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "volume": 10.0,
            "entry_side": None,
            "breakout_side": "short",
            "state_1m": "RANGE",
            "state_5m": "BREAKOUT",
            "context_15m": "RANGE",
            "structural_direction": "long",
            "sma_gap_bps": 2.0,
            "regime_strength_score": 0.5,
            "bbwp_percentile": 20.0,
            "ema_gap_bps_signed": 1.0,
            "rsi": 50.0,
            "breakout_volume_ratio": 1.0,
            "regime_5m_strength_percentile": 65.0,
            "regime_5m_bbwp_percentile": 20.0,
            "regime_5m_ema_gap_bps": 6.0,
            "regime_5m_breakout_volume_ratio": 3.0,
            "funding_rate": 0.0,
        },
        index=index,
    )
    market.loc[index[64], "entry_side"] = "long"
    market.loc[index[66] :, "structural_direction"] = "short"
    market.loc[index[66], "entry_side"] = "short"
    return market


def _config() -> HypeExitReplayConfig:
    return HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=5,
        exit_on_opposite_signal=True,
    )


def test_alignment_replay_recomputes_occupancy_from_signal_time() -> None:
    """Removing an opposed opener must free the later aligned signal."""
    bundle = build_hype_compression_alignment_replay(
        _market(),
        (_market(),),
        frozen_policy_id="compression_5m50_1m40_pullback",
        config=_config(),
        fold_count=2,
    )

    control = bundle.development_trades.loc[
        bundle.development_trades["cohort"].eq("control")
    ]
    aligned = bundle.development_trades.loc[
        bundle.development_trades["cohort"].eq("aligned_only")
    ]

    assert control.iloc[0]["signal_time_utc"] == _market().index[64].isoformat()
    assert aligned.iloc[0]["signal_time_utc"] == _market().index[66].isoformat()
    assert bundle.report["development"]["control"]["occupied_signals"] == 1
    assert bundle.report["development"]["aligned_only"]["occupied_signals"] == 0


def test_alignment_market_builder_exposes_exact_frozen_cohorts() -> None:
    """The public builder returns aligned signals without replaying exits."""
    result = build_hype_compression_alignment_markets(
        _market(),
        frozen_policy_id="compression_5m50_1m40_pullback",
    )

    aligned = result.markets["aligned_only"]["entry_side"].dropna()
    assert aligned.to_dict() == {_market().index[66]: "short"}
    assert result.accounting["aligned_onsets"] == 1
    assert result.compression.eligible_signals == 2


def test_alignment_replay_is_frozen_report_only_and_side_separated() -> None:
    """The challenger preserves v51 execution and exposes both sides."""
    bundle = build_hype_compression_alignment_replay(
        _market(),
        (_market(),),
        frozen_policy_id="compression_5m50_1m40_pullback",
        config=_config(),
        fold_count=2,
    )

    report = bundle.report
    assert report["execution_authority"] == "none"
    assert report["selection_performed"] is False
    assert report["contract"]["frozen_compression_policy_id"] == (
        "compression_5m50_1m40_pullback"
    )
    assert report["contract"]["execution"]["exit_on_opposite_signal"] is True
    assert set(report["development"]) == {
        "control",
        "aligned_only",
        "opposed_only",
    }
    assert set(report["development"]["aligned_only"]["side_summary"]) == {
        "long",
        "short",
    }
    assert report["development"]["aligned_only"]["chronological_fold_count"] == 2


def test_confirmation_censors_segment_boundary_lifecycles() -> None:
    """A segment-end force close cannot count as a resolved later trade."""
    short = _market().iloc[:68]

    bundle = build_hype_compression_alignment_replay(
        _market(),
        (short,),
        frozen_policy_id="compression_5m50_1m40_pullback",
        config=_config(),
        fold_count=2,
    )

    confirmation = bundle.report["later_confirmation"]["aligned_only"]
    assert confirmation["resolved_trades"] == 0
    assert confirmation["censored_lifecycles"] == 1
    rows = bundle.confirmation_trades.loc[
        bundle.confirmation_trades["cohort"].eq("aligned_only")
    ]
    assert rows["censored"].tolist() == [True]
