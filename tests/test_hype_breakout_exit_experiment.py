"""Selection-contract tests for the HYPE exit experiment."""

from __future__ import annotations

import pandas as pd

import hypervector.research.hype_breakout_exit_experiment as exit_experiment
from hypervector.research.hype_breakout_exit_experiment import (
    HypePolicyDevelopment,
    build_breakout_entry_direction_comparison,
    build_hype_momentum_exit_comparison,
    select_hype_exit_policy,
    split_hype_exit_market,
)
from hypervector.research.hype_breakout_exit_replay import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
)


def _report(policy_id: str, net: float, drawdown: float) -> HypeExitReplayReport:
    profit = max(net, 0.0)
    loss = max(-net, 0.0)
    return HypeExitReplayReport(
        policy_id=policy_id,
        completed_trades=10,
        wins=5,
        losses=5,
        net_return_bps=net,
        gross_profit_bps=profit,
        gross_loss_bps=loss,
        profit_factor=profit / loss if loss else None,
        maximum_drawdown_bps=drawdown,
        total_fee_bps=90.0,
        funding_bps=0.0,
        occupied_signals=0,
        exit_reasons={},
        monthly_net_bps={},
        trades=(),
    )


def _development(
    policy_id: str,
    net: float,
    folds: tuple[float, ...],
    drawdown: float,
) -> HypePolicyDevelopment:
    return HypePolicyDevelopment(
        HypeExitPolicy(policy_id, exit_on_invalidation=True),
        _report(policy_id, net, drawdown),
        folds,
    )


def test_selection_prefers_temporal_stability_before_aggregate_windfall() -> None:
    """One exceptional fold cannot outrank a broadly positive challenger."""
    unstable = _development(
        "unstable", 1_000.0, (-50.0, -20.0, -10.0, 0.0, 1_080.0), 500.0
    )
    stable = _development("stable", 100.0, (20.0, 20.0, 20.0, 20.0, 20.0), 50.0)

    selected = select_hype_exit_policy((unstable, stable))

    assert selected.policy.policy_id == "stable"
    assert selected.positive_folds == 5
    assert selected.median_fold_net_bps == 20.0


def test_selection_is_deterministic_on_an_exact_metric_tie() -> None:
    """Policy identity supplies the final documented deterministic tie-break."""
    beta = _development("beta", 100.0, (20.0,) * 5, 50.0)
    alpha = _development("alpha", 100.0, (20.0,) * 5, 50.0)

    selected = select_hype_exit_policy((beta, alpha))

    assert selected.policy.policy_id == "alpha"


def test_extension_split_purges_the_full_hard_lifecycle() -> None:
    """A 24-hour extension cannot leak a development trade into holdout."""
    index = pd.date_range("2026-01-01", periods=3 * 24 * 60, freq="1min", tz="UTC")
    market = pd.DataFrame(index=index)
    config = HypeExitReplayConfig(
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
    )

    _, _, split = split_hype_exit_market(market, config, holdout_days=1)

    assert split["purge_minutes"] == 1_440
    assert split["development_end_exclusive_utc"] == "2026-01-02T00:00:00+00:00"


def test_live_extension_comparison_retains_both_policies_without_authority() -> None:
    """Parity research must preserve fixed and live exit outcomes side by side."""
    index = pd.date_range("2026-01-01", periods=4 * 24 * 60, freq="1min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_5m": "TREND_UP",
            "state_1m": "TREND_UP",
            "context_15m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    market.loc[index[0], "entry_side"] = "long"
    market.loc[index[4_800], "entry_side"] = "long"
    builder = getattr(exit_experiment, "build_hype_live_extension_comparison", None)

    assert callable(builder)
    report = builder(market, holdout_days=1)

    assert report["execution_authority"] == "none"
    assert report["contract"]["performance_gate"] is False
    assert report["trial_accounting"]["current_policy_trials"] == 4
    assert set(report["development"]) == {"fixed_8h", "live_extension_8h_to_24h"}
    assert report["development"]["fixed_8h"]["completed_trades"] == 1
    assert report["development"]["live_extension_8h_to_24h"]["exit_reasons"] == {
        "hard_maximum_hold": 1
    }


def test_entry_direction_comparison_is_report_only_and_keeps_both_arms() -> None:
    """A direction challenger must isolate entry side without gaining authority."""
    index = pd.date_range("2026-01-01", periods=4 * 24 * 60, freq="1min", tz="UTC")
    base = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_5m": "TREND_UP",
            "state_1m": "TREND_UP",
            "context_15m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    structural = base.copy()
    directional = base.copy()
    structural.loc[index[0], "entry_side"] = "long"
    structural.loc[index[4_800], "entry_side"] = "long"
    directional.loc[index[0], "entry_side"] = "short"
    directional.loc[index[4_800], "entry_side"] = "short"

    report = build_breakout_entry_direction_comparison(
        structural,
        directional,
        holdout_days=1,
    )

    assert report["execution_authority"] == "none"
    assert report["report_only"] is True
    assert report["contract"]["same_breakout_onsets"] is True
    assert set(report["development"]) == {
        "hourly_structural_side",
        "breakout_continuation_side",
    }
    assert report["trial_accounting"] == {"predeclared_entry_arms": 2}


def test_momentum_exit_comparison_is_report_only_and_keeps_control() -> None:
    """The completed-5m challenger must remain paired with live exit mechanics."""
    index = pd.date_range("2026-01-01", periods=4 * 24 * 60, freq="1min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_5m": "TREND_UP",
            "state_1m": "TREND_UP",
            "context_15m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
            "regime_5m_rsi": 55.0,
            "regime_5m_rsi_ema": 50.0,
        },
        index=index,
    )
    market.loc[index[0], "entry_side"] = "long"
    market.loc[index[4_800], "entry_side"] = "long"

    report = build_hype_momentum_exit_comparison(market, holdout_days=1)

    assert report["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert set(report["development"]) == {
        "live_extension_8h_to_24h",
        "five_minute_momentum_reversal",
    }
    assert report["trial_accounting"] == {"predeclared_exit_arms": 2}


def test_entry_direction_comparison_reports_and_excludes_unpaired_onsets() -> None:
    """Neutral structural onsets cannot silently enter only one comparison arm."""
    index = pd.date_range("2026-01-01", periods=4 * 24 * 60, freq="1min", tz="UTC")
    base = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_5m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    structural = base.copy()
    breakout = base.copy()
    structural.loc[index[0], "entry_side"] = "long"
    structural.loc[index[4_800], "entry_side"] = "long"
    breakout.loc[index[0], "entry_side"] = "short"
    breakout.loc[index[100], "entry_side"] = "long"
    breakout.loc[index[4_800], "entry_side"] = "short"

    report = build_breakout_entry_direction_comparison(
        structural,
        breakout,
        holdout_days=1,
    )

    assert report["entry_accounting"] == {
        "compared_onsets": 2,
        "hourly_structural_only_onsets": 0,
        "breakout_direction_only_onsets": 1,
    }
    assert report["development"]["hourly_structural_side"]["completed_trades"] == 1
    assert report["development"]["breakout_continuation_side"]["completed_trades"] == 1
