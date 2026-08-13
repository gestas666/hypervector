"""Tests for the report-only HYPE compression-breakout challenger."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hype_breakout_entry_features import build_hype_entry_features
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_compression_breakout_challenger import (
    apply_hype_compression_policy,
    build_hype_compression_breakout_bundle,
    build_hype_compression_confirmation,
    declared_hype_compression_policies,
)


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=100, freq="1min", tz="UTC")
    close = pd.Series([100.0] * len(index), index=index)
    entry = [None] * len(index)
    entry[64] = "long"
    entry[84] = "short"
    body_open = close.copy()
    body_open.iloc[64] = 100.1
    body_open.iloc[84] = 99.9
    bbwp = [50.0] * len(index)
    bbwp[49] = 20.0
    bbwp[69] = 20.0
    return pd.DataFrame(
        {
            "open": body_open,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": [10.0] * len(index),
            "entry_side": entry,
            "state_5m": ["BREAKOUT"] * len(index),
            "state_1m": ["RANGE"] * len(index),
            "context_15m": ["RANGE"] * len(index),
            "structural_direction": ["long"] * 74 + ["short"] * 26,
            "sma_gap_bps": [2.0] * len(index),
            "regime_strength_score": [0.5] * len(index),
            "bbwp_percentile": bbwp,
            "ema_gap_bps_signed": [1.0] * len(index),
            "rsi": [50.0] * len(index),
            "breakout_volume_ratio": [1.0] * len(index),
            "regime_5m_strength_percentile": [65.0] * len(index),
            "regime_5m_bbwp_percentile": [35.0] * 75 + [55.0] * 25,
            "regime_5m_ema_gap_bps": [6.0] * len(index),
            "regime_5m_breakout_volume_ratio": [3.0] * len(index),
            "funding_rate": [0.0] * len(index),
        },
        index=index,
    )


def test_declared_compression_policies_are_frozen_and_bounded() -> None:
    """The experiment contains one control and three declared mechanisms."""
    policies = declared_hype_compression_policies()

    assert [policy.policy_id for policy in policies] == [
        "hype_breakout_control",
        "compression_5m40_1m40_pullback",
        "compression_5m50_1m40_pullback",
        "compression_5m50_1m50_pullback",
    ]
    assert all(policy.preserve_breakout_onset for policy in policies)


def test_compression_policy_filters_only_entry_events() -> None:
    """A rejected setup cannot change bars, funding, or source regimes."""
    market = _market()
    features = build_hype_entry_features(market)
    policy = declared_hype_compression_policies()[1]

    filtered, evidence = apply_hype_compression_policy(market, features, policy)

    assert evidence.raw_signals == 2
    assert evidence.eligible_signals == 1
    assert evidence.rejected_signals == 1
    assert filtered["entry_side"].notna().sum() == 1
    assert filtered.drop(columns="entry_side").equals(market.drop(columns="entry_side"))


def test_policy_decisions_are_invariant_to_future_rows() -> None:
    """Appending later observations cannot rewrite prior eligibility."""
    market = _market()
    features = build_hype_entry_features(market)
    policy = declared_hype_compression_policies()[3]
    prior, prior_evidence = apply_hype_compression_policy(market, features, policy)
    future = market.iloc[-1:].copy()
    future.index = future.index + pd.Timedelta(minutes=1)
    extended = pd.concat([market, future])
    extended_features = build_hype_entry_features(extended)

    revised, revised_evidence = apply_hype_compression_policy(
        extended,
        extended_features,
        policy,
    )

    assert revised.loc[market.index, "entry_side"].equals(prior["entry_side"])
    assert revised_evidence == prior_evidence


def test_bundle_reports_all_trials_without_execution_authority() -> None:
    """Development selection is visible but cannot authorize execution."""
    bundle = build_hype_compression_breakout_bundle(
        _market(),
        config=HypeExitReplayConfig(maximum_hold_minutes=5),
        fold_count=2,
    )

    assert bundle.report["execution_authority"] == "none"
    assert bundle.report["evidence_status"] == "post_hoc_development_only"
    assert bundle.report["trial_accounting"]["current_policy_trials"] == 4
    assert set(bundle.report["development"]) == {
        policy.policy_id for policy in declared_hype_compression_policies()
    }
    assert bundle.report["selection"]["holdout_used"] is False
    assert set(bundle.trade_rows["policy_id"]) == set(bundle.report["development"])


def test_confirmation_keeps_development_identity_frozen() -> None:
    """Later evidence compares a fixed policy and cannot reselect another arm."""
    policy_id = "compression_5m50_1m40_pullback"

    confirmation = build_hype_compression_confirmation(
        (_market(),),
        frozen_policy_id=policy_id,
        config=HypeExitReplayConfig(maximum_hold_minutes=5),
    )

    assert confirmation.report["execution_authority"] == "none"
    assert confirmation.report["frozen_policy_id"] == policy_id
    assert confirmation.report["selection_performed"] is False
    assert set(confirmation.report["confirmation"]) == {
        "hype_breakout_control",
        policy_id,
    }


def test_confirmation_censors_lifecycle_crossing_a_data_boundary() -> None:
    """A forced close at an archive gap cannot masquerade as a resolved trade."""
    incomplete = _market().iloc[:66]
    later = _market().copy()
    later.index = later.index + pd.Timedelta(days=1)

    confirmation = build_hype_compression_confirmation(
        (incomplete, later),
        frozen_policy_id="compression_5m50_1m40_pullback",
        config=HypeExitReplayConfig(maximum_hold_minutes=5),
    )

    selected = confirmation.report["confirmation"]["compression_5m50_1m40_pullback"]
    assert confirmation.report["evidence_status"] == "technically_unresolved"
    assert selected["unresolved_gap_lifecycles"] == 1
    rows = confirmation.trade_rows.loc[
        confirmation.trade_rows["policy_id"].eq("compression_5m50_1m40_pullback")
    ]
    assert int(rows["censored"].sum()) == 1
    assert selected["metrics"]["completed_trades"] == int((~rows["censored"]).sum())
