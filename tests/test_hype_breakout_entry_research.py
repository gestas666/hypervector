"""Bounded development tests for HYPE breakout entry policies."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hype_breakout_entry_features import build_hype_entry_features
from hypervector.research.hype_breakout_entry_research import (
    apply_hype_entry_policy,
    build_hype_entry_research_bundle,
    declared_hype_entry_policies,
    run_hype_entry_research,
)
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=80, freq="1min", tz="UTC")
    close = pd.Series([100.0] * 80, index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": [10.0] * 80,
            "entry_side": [None] * 64 + ["long"] + [None] * 14 + ["short"],
            "state_5m": ["BREAKOUT"] * 80,
            "state_1m": ["RANGE"] * 80,
            "context_15m": ["RANGE"] * 80,
            "structural_direction": ["long"] * 65 + ["short"] * 15,
            "sma_gap_bps": [2.0] * 80,
            "regime_strength_score": [0.5] * 80,
            "bbwp_percentile": [50.0] * 49
            + [20.0]
            + [50.0] * 14
            + [90.0]
            + [50.0] * 15,
            "ema_gap_bps_signed": [1.0] * 80,
            "rsi": [50.0] * 80,
            "breakout_volume_ratio": [1.0] * 80,
            "regime_5m_strength_percentile": [65.0] * 80,
            "regime_5m_bbwp_percentile": [35.0] * 80,
            "regime_5m_ema_gap_bps": [6.0] * 80,
            "regime_5m_breakout_volume_ratio": [3.0] * 80,
            "funding_rate": [0.0] * 80,
        },
        index=index,
    )


def test_declared_entry_policies_are_bounded_and_mechanistic() -> None:
    """The post-hoc screen contains one control and three declared revisions."""
    policies = declared_hype_entry_policies()

    assert [policy.policy_id for policy in policies] == [
        "hype_breakout_control",
        "pullback_body_nonpositive",
        "precompression15_min40",
        "precompression15_min40_pullback",
    ]


def test_entry_policy_filters_only_source_events() -> None:
    """Rejected entries do not alter bars, funding, or other market evidence."""
    market = _market()
    features = build_hype_entry_features(market)
    policy = declared_hype_entry_policies()[2]

    filtered, evidence = apply_hype_entry_policy(market, features, policy)

    assert evidence.raw_signals == 2
    assert evidence.eligible_signals == 1
    assert filtered["entry_side"].notna().sum() == 1
    assert filtered.drop(columns="entry_side").equals(market.drop(columns="entry_side"))


def test_entry_research_counts_search_and_denies_execution_authority() -> None:
    """Development evidence reports every trial without promoting live behavior."""
    market = _market()
    report = run_hype_entry_research(
        market,
        config=HypeExitReplayConfig(maximum_hold_minutes=5),
        fold_count=2,
    )

    assert report["execution_authority"] == "none"
    assert report["evidence_status"] == "post_hoc_development_only"
    assert report["trial_accounting"]["current_system_policy_trials"] == 4
    assert report["trial_accounting"]["cumulative_known_economic_trials"] == 36
    assert set(report["development"]) == {
        policy.policy_id for policy in declared_hype_entry_policies()
    }

    bundle = build_hype_entry_research_bundle(
        market,
        config=HypeExitReplayConfig(maximum_hold_minutes=5),
        fold_count=2,
    )
    assert set(bundle.trade_rows["policy_id"]) == {
        policy.policy_id for policy in declared_hype_entry_policies()
    }
    assert bundle.report == report
