"""Bounded-mechanism tests for HYPE breakout profit research."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hype_breakout_exit_models import HypeExitTrade
from hypervector.research.hype_breakout_profit_research import (
    build_hype_profit_research_bundle,
    declared_hype_profit_policies,
    freeze_hype_entry_cohort,
    run_hype_profit_research,
    summarize_hype_excursions,
)


def _trade(
    *,
    gross_bps: float,
    net_bps: float,
    mfe_bps: float,
    mae_bps: float,
) -> HypeExitTrade:
    return HypeExitTrade(
        side="long",
        signal_time_utc="2026-01-01T00:00:00+00:00",
        entry_time_utc="2026-01-01T00:01:00+00:00",
        exit_time_utc="2026-01-01T00:02:00+00:00",
        entry_price=100.0,
        exit_price=100.0 + gross_bps / 100.0,
        stop_price=99.2,
        gross_return_bps=gross_bps,
        fee_bps=9.0,
        funding_bps=0.0,
        net_return_bps=net_bps,
        hold_minutes=1,
        maximum_favorable_excursion_bps=mfe_bps,
        maximum_adverse_excursion_bps=mae_bps,
        exit_reason="maximum_hold",
    )


def test_declared_profit_policies_are_bounded_and_cost_aware() -> None:
    """The search contains one control and only three predeclared mechanisms."""
    policies = declared_hype_profit_policies()

    assert len(policies) == 4
    assert policies[0].policy_id == "generic_8h_control"
    assert [policy.profit_activation_bps for policy in policies[1:]] == [
        25.0,
        40.0,
        60.0,
    ]
    assert all(policy.profit_floor_bps == 15.0 for policy in policies[1:])


def test_excursion_summary_exposes_headroom_and_giveback() -> None:
    """MFE coverage and realized giveback remain distinct measurements."""
    trades = (
        _trade(gross_bps=5.0, net_bps=-4.0, mfe_bps=10.0, mae_bps=5.0),
        _trade(gross_bps=-10.0, net_bps=-19.0, mfe_bps=30.0, mae_bps=20.0),
    )

    summary = summarize_hype_excursions(trades)

    assert summary["mfe_bps_quantiles"]["p50"] == pytest.approx(20.0)
    assert summary["mae_bps_quantiles"]["p50"] == pytest.approx(12.5)
    assert summary["mfe_threshold_coverage"]["15bps"] == pytest.approx(0.5)
    assert summary["median_favorable_giveback_bps"] == pytest.approx(22.5)
    assert summary["trades"] == 2


def test_excursion_summary_requires_at_least_one_trade() -> None:
    """An empty lifecycle sample cannot become success-shaped zero evidence."""
    with pytest.raises(ValueError, match="at least one trade"):
        summarize_hype_excursions(())


def test_profit_research_retains_trial_count_and_denies_live_authority() -> None:
    """Post-hoc exploration remains counted and cannot promote itself."""
    index = pd.date_range("2026-01-01", periods=20, freq="1min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": [100.0] * 20,
            "high": [100.7] * 20,
            "low": [99.9] * 20,
            "close": [100.5] * 20,
            "entry_side": ["long", *([None] * 19)],
            "state_5m": ["BREAKOUT"] * 20,
            "structural_direction": ["long"] * 20,
            "funding_rate": [0.0] * 20,
        },
        index=index,
    )

    report = run_hype_profit_research(market, fold_count=2)

    assert report["execution_authority"] == "none"
    assert report["evidence_status"] == "post_hoc_exploration_only"
    assert report["trial_accounting"] == {
        "prior_exit_trials": 24,
        "current_system_policy_trials": 4,
        "matched_entry_diagnostic_trials": 4,
        "cumulative_known_trials": 32,
    }
    assert report["forward_candidate"]["policy_id"] is None
    assert report["forward_candidate"]["status"] == "no_challenger_outperformed_control"
    assert report["least_bad_challenger"]["policy_id"].startswith("profit_")
    assert report["control_excursions"]["trades"] == 1

    bundle = build_hype_profit_research_bundle(market, fold_count=2)
    assert len(bundle.trade_rows) == 8
    assert set(bundle.trade_rows["policy_id"]) == {
        policy.policy_id for policy in declared_hype_profit_policies()
    }
    assert "maximum_favorable_excursion_bps" in bundle.trade_rows
    assert set(bundle.trade_rows["analysis_scope"]) == {
        "full_system",
        "matched_control_entries",
    }


def test_fixed_entry_cohort_removes_only_noncontrol_onsets() -> None:
    """Exit quality can be measured without admitting newly freed-capital entries."""
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    market = pd.DataFrame(
        {
            "entry_side": ["long", "short", None, "long", None],
        },
        index=index,
    )
    control = (_trade(gross_bps=5.0, net_bps=-4.0, mfe_bps=10.0, mae_bps=5.0),)
    control = (
        HypeExitTrade(
            **{
                **control[0].__dict__,
                "signal_time_utc": index[0].isoformat(),
                "side": "long",
            }
        ),
    )

    frozen = freeze_hype_entry_cohort(market, control)

    assert frozen["entry_side"].tolist() == ["long", None, None, None, None]
