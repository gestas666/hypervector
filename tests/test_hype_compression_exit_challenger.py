"""Tests for the frozen HYPE-compression exit challenger."""

from __future__ import annotations

import pandas as pd

from hypervector.research import hype_compression_regime_loss_exit as regime_loss
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_compression_exit_challenger import (
    build_hype_compression_exit_study,
    declared_hype_compression_exit_policies,
)


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=180, freq="1min", tz="UTC")
    close = pd.Series(100.0, index=index)
    entry: list[str | None] = [None] * len(index)
    entry[64], entry[124] = "long", "short"
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.4,
            "low": close - 0.2,
            "close": close,
            "volume": 10.0,
            "entry_side": entry,
            "state_1m": "RANGE",
            "state_5m": "BREAKOUT",
            "context_15m": "RANGE",
            "structural_direction": ["long"] * 100 + ["short"] * 80,
            "sma_gap_bps": 2.0,
            "regime_strength_score": 0.5,
            "bbwp_percentile": 20.0,
            "ema_gap_bps_signed": 1.0,
            "rsi": 50.0,
            "breakout_volume_ratio": 1.0,
            "regime_5m_strength_percentile": 65.0,
            "regime_5m_bbwp_percentile": 35.0,
            "regime_5m_ema_gap_bps": 6.0,
            "regime_5m_breakout_volume_ratio": 3.0,
            "funding_rate": 0.0,
        },
        index=index,
    )


def test_exit_grid_is_predeclared_and_reset_aware() -> None:
    """The challenger varies only exit mechanics after a frozen entry policy."""
    policies = declared_hype_compression_exit_policies()

    assert [policy.policy_id for policy in policies] == [
        "compression_live_exit_control",
        "compression_a25_reset",
        "compression_a40_reset",
        "compression_a60_reset",
    ]
    assert all(policy.reentry_requires_structural_reset for policy in policies[1:])


def test_study_selects_on_development_and_only_scores_frozen_exit_later() -> None:
    """Later evidence cannot choose a different compression or exit identity."""
    bundle = build_hype_compression_exit_study(
        _market(),
        (_market(),),
        frozen_compression_policy_id="compression_5m50_1m40_pullback",
        config=HypeExitReplayConfig(maximum_hold_minutes=20),
        fold_count=2,
    )

    report = bundle.report
    selected = report["development_selection"]["selected_exit_policy_id"]
    assert report["execution_authority"] == "none"
    assert report["frozen_compression_policy_id"] == ("compression_5m50_1m40_pullback")
    assert report["later_confirmation"]["selection_performed"] is False
    assert report["disposition"] in {
        "retain_control_exit",
        "challenger_requires_new_forward_evidence",
    }
    assert isinstance(report["development_acceptance"]["passed"], bool)
    assert set(report["later_confirmation"]["policies"]) == {
        "compression_live_exit_control",
        selected,
    }
    assert set(bundle.development_trades["exit_policy_id"]) == {
        policy.policy_id for policy in declared_hype_compression_exit_policies()
    }


def test_regime_loss_study_freezes_one_policy_and_never_reselects_later() -> None:
    """The transferred opposition exit is one declared test, not another grid."""
    study = regime_loss.build_hype_compression_regime_loss_study(
        _market(),
        (_market(),),
        frozen_compression_policy_id="compression_5m50_1m40_pullback",
        config=HypeExitReplayConfig(maximum_hold_minutes=20),
        fold_count=2,
    )

    assert study.report["execution_authority"] == "none"
    assert study.report["policy_id"] == "opp5_loss20"
    assert study.report["trial_count"] == 1
    assert study.report["later_confirmation"]["selection_performed"] is False
    assert study.report["capital_reallocation_modeled"] is False
    assert (
        len(study.development_trades) == study.report["development"]["entry_lifecycles"]
    )
