"""Source-bound acceptance for the v49 strategy repair disposition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_observer_regime_interactions import (
    build_observer_regime_interactions,
)
from hypervector.research.v49_risk_balanced_sizing import (
    build_v49_risk_balanced_sizing,
)

_CONFIG = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")
_REPORT = Path("docs/research-journal/v49-strategy-repair-disposition.json")
_RESEARCH = Path("data/logs/research")
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/v49_growth_sizing_stress_20260812_v1.json"
)
_DRAG = Path(
    "data/logs/research/bidirectional_cohort/"
    "v39_execution_cash_drag_20260812T1806Z_v1.json"
)
_ROUTE_REVIEW = Path(
    "data/logs/research/bidirectional_cohort/"
    "v39_route_portfolio_review_20260812T1830Z_v1.json"
)
_REGIME = Path(
    "data/logs/research/bidirectional_cohort/"
    "v39_regime_forward_accuracy_20260812T1832Z_v1.json"
)
_V49_REGIME = Path(
    "data/logs/research/bidirectional_cohort/"
    "v49_observer_regime_forward_accuracy_20260813T0214Z_v4.json"
)
_MU_DIAGNOSTIC = Path(
    "data/logs/research/"
    "xyz_mu_15m_breakout_development_path_thresholds_20260608_20260716_v1.json"
)
_MU_PARITY = _RESEARCH / "xyz_mu_prospective_signal_parity_20260812T0915Z_v2.json"
_SKHX_DIAGNOSTIC = Path(
    "data/logs/research/xyz_skhx_development_only_diagnostic_20260812_v5.json"
)
_SKHX_PARITY = _RESEARCH / "xyz_skhx_prospective_signal_parity_20260812T0900Z_v10.json"
_CL_DIAGNOSTIC = Path(
    "data/logs/research/xyz_cl_development_only_diagnostic_20260811_v1.json"
)
_SILVER_DIAGNOSTIC = Path(
    "data/logs/research/xyz_silver_development_only_diagnostic_20260811_v1.json"
)
_MU_MARKOUTS = _RESEARCH / "xyz_mu_prospective_bbo_markouts_20260812T1850Z_v1.json"
_CL_MARKOUTS = _RESEARCH / "xyz_cl_prospective_bbo_markouts_20260812T1850Z_v1.json"
_TRADE_ORACLE_REVIEW = Path(
    "docs/research-journal/v49-trade-oracle-challenge-20260812.md"
)
_SOL_ELIGIBLE_FORWARD = Path(
    "data/logs/research/bidirectional_cohort/"
    "v49_observer_sol_range_eligible_policy_20260812_v1.json"
)
_SOL_PROFIT_LOCK_FORWARD = Path(
    "data/logs/research/v49_sol_profit_lock_forward_20260812_v1.json"
)
_SOL_PROFIT_LOCK_CONTINUATION = Path(
    "data/logs/research/v49_sol_profit_lock_forward_20260812_v2.json"
)
_HIP3_SWING_REPORTS = (
    Path("data/logs/research/hip3_swing_ha_transfer_sndk_gold_disabled_brent_v1.json"),
    Path("data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.json"),
)
_EXACT_OBSERVER_REPORTS = {
    "sol_missing_hourly_cross_15m": Path(
        "data/logs/research/bidirectional_cohort/"
        "v49_observer_sol_hourly_cross_nearmiss_exact_depth_15m_20260812_v2.json"
    ),
    "hype_missing_compression_60m": Path(
        "data/logs/research/bidirectional_cohort/"
        "v49_observer_hype_compression_nearmiss_exact_depth_60m_20260812_v2.json"
    ),
    "hype_missing_onset_15m": Path(
        "data/logs/research/bidirectional_cohort/"
        "v49_observer_hype_onset_nearmiss_exact_depth_15m_20260812_v2.json"
    ),
    "hype_missing_onset_60m": Path(
        "data/logs/research/bidirectional_cohort/"
        "v49_observer_hype_onset_nearmiss_exact_depth_60m_20260812_v2.json"
    ),
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.evidence
def test_v49_disposition_matches_exact_profile_and_stress() -> None:
    """Disposition identity and $5K risk must match immutable evidence."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    report = _load(_REPORT)
    stress = _load(_STRESS)
    scenario = next(
        row for row in stress["scenarios"] if row["account_value_usd"] == 5_000.0
    )

    assert report["profile_id"] == config.profile_id
    assert report["profile_fingerprint"] == config.profile_fingerprint
    assert stress["profile_fingerprint"] == config.profile_fingerprint
    assert report["modeled_p99_stop_wave_usd_at_5000"] == pytest.approx(
        scenario["stacked_p99_stop_wave_loss_usd"]
    )
    assert report["modeled_p99_stop_wave_pct_at_5000"] == pytest.approx(
        scenario["stacked_p99_stop_wave_loss_pct_equity"]
    )


def test_v49_disposition_distinguishes_repair_from_weak_edge() -> None:
    """Real contract defects must remain distinct from outlier-dependent routes."""
    report = _load(_REPORT)
    repairs = {row["component"]: row for row in report["confirmed_repairs"]}
    retired = {row["strategy"]: row for row in report["reconsidered_but_not_restored"]}

    assert repairs["SOL Range stop contract"]["repair"].startswith(
        "retain ETH at 60 bps"
    )
    assert repairs["mixed-roster canonical regime observation"][
        "execution_effect"
    ].startswith("research telemetry only")
    assert retired["Hulk Expansion bidirectional v2"]["finding"].startswith(
        "The all-time live slice looks positive"
    )
    assert (
        "do not repeat the falsified SOL v3 transfer"
        in retired["Hulk Expansion bidirectional v2"]["decision"]
    )
    assert retired["HIP-3 Swing"]["decision"].startswith(
        "keep the unchanged identity retired"
    )
    assert report["execution_authority"] == "none"


@pytest.mark.evidence
def test_v49_swing_retirement_includes_literal_and_tuned_failures() -> None:
    """Swing must not be called a bug when both exact mechanisms failed validation."""
    report = _load(_REPORT)
    retired = {row["strategy"]: row for row in report["reconsidered_but_not_restored"]}

    for path in _HIP3_SWING_REPORTS:
        source = _load(path)
        for cohort in ("literal_9x21_control_nominal", "nominal"):
            rows = source["validation"][cohort]
            assert rows
            assert all(row["net_pnl_usd"] < 0.0 for row in rows)
        assert str(path) in report["evidence_paths"]
    assert "green-plus-buy/red-plus-sell" in retired["HIP-3 Swing"]["finding"]


@pytest.mark.evidence
def test_v49_observer_status_is_source_bound_and_technically_complete() -> None:
    """Observer claims must reconcile to the live read-only checkpoint."""
    report = _load(_REPORT)
    checkpoint = _load(Path(report["evidence_paths"][-1]))
    observer = checkpoint["observer"]
    technical = checkpoint["audit"]["technical"]

    assert report["observer_status"]["run_id"] == observer["run_id"]
    assert (
        report["observer_status"]["effective_profile_fingerprint"]
        == (checkpoint["audit"]["run"]["profile_fingerprint"])
    )
    assert (
        report["observer_status"]["base_profile_fingerprint"]
        == report["profile_fingerprint"]
    )
    assert technical["complete"] is True
    assert technical["observed_provider_symbols"] == 5
    canonical = checkpoint["audit"]["canonical_regime_telemetry"]
    assert (
        sorted(canonical["by_symbol"])
        == report["observer_status"]["canonical_regime_symbols"]
    )
    assert canonical["contract"]["execution_authority"] == "none"
    assert checkpoint["checkpoint_contract"]["execution_authority"] == "none"


@pytest.mark.evidence
def test_v49_exit_and_sizing_decisions_reconcile_to_frozen_evidence() -> None:
    """Exit and sizing recommendations must remain arithmetic, not intuition."""
    report = _load(_REPORT)
    sizing = build_v49_risk_balanced_sizing(_load(_STRESS))
    decision = report["exit_and_sizing_disposition"]

    assert decision["eth_range_max_hold_winners"] == 7
    assert decision["eth_range_max_hold_net_usd"] == pytest.approx(3798.8958495012616)
    assert decision["risk_balanced_p99_loss_usd"] == pytest.approx(
        sizing["comparison"]["candidate_p99_loss_usd"]
    )
    assert decision["risk_balanced_total_margin_fraction"] == pytest.approx(0.6)
    assert decision["risk_balanced_automatic_change"] is False


@pytest.mark.evidence
def test_v49_disposition_reconciles_current_live_execution_drag() -> None:
    """Retired-route friction claims must bind exact resolved live trades."""
    report = _load(_REPORT)
    drag = _load(_DRAG)["diagnostic"]["performance"]["total"]
    decision = report["live_execution_drag_disposition"]

    assert decision["closed_trades"] == drag["closed_trades"] == 15
    assert decision["execution_cash_drag_usd"] == pytest.approx(
        drag["execution_cash_drag_usd"]
    )
    assert decision["execution_cash_drag_pct_positive_gross"] == pytest.approx(
        drag["execution_cash_drag_as_pct_of_positive_gross_market_pnl"]
    )
    assert decision["automatic_strategy_change"] is False


@pytest.mark.evidence
def test_v49_disposition_preserves_current_lifecycle_root_causes() -> None:
    """Frozen exit causes must reconcile to the frozen route-review totals."""
    report = _load(_REPORT)
    route_review = _load(_ROUTE_REVIEW)
    decision = report["live_lifecycle_root_cause_disposition"]

    reasons = decision["exit_reason_totals"]
    assert set(reasons) == {
        "protective_stop",
        "maximum_hold_seconds",
        "opposite_strategy_intent",
    }
    assert (
        sum(row["closed_trades"] for row in reasons.values())
        == (route_review["summary"]["current_run_closed_trades"])
    )
    assert sum(row["net_pnl_usd"] for row in reasons.values()) == pytest.approx(
        route_review["summary"]["current_run_net_pnl_usd"]
    )
    assert decision["stale_hip3_pressure_closes"] == 5
    assert decision["opposite_exit_adverse_60m_paths"] == 3
    assert decision["automatic_strategy_change"] is False
    assert str(_ROUTE_REVIEW) in report["evidence_paths"]


@pytest.mark.evidence
def test_v49_regime_disposition_uses_episode_onsets_not_repeated_rows() -> None:
    """Regime use must bind sparse causal onsets instead of autocorrelated rows."""
    report = _load(_REPORT)
    regime = _load(_REGIME)
    decision = report["regime_disposition"]["latest_v39_onset_accuracy"]

    assert decision["unique_observations"] == regime["source"]["unique_observations"]
    for horizon, expected in decision["by_horizon"].items():
        onsets = regime["horizons"][horizon]["state_fields"]["primary_regime"]
        clusters = onsets["episode_onset_clusters"]
        for state in ("TREND_UP", "TREND_DOWN"):
            assert expected[state]["observations"] == clusters[state]["observations"]
            assert expected[state]["directional_accuracy_pct"] == pytest.approx(
                clusters[state]["directional_accuracy_pct"]
            )
    assert report["regime_disposition"]["automatic_leverage_change"] is False
    assert str(_REGIME) in report["evidence_paths"]


@pytest.mark.evidence
def test_v49_regime_disposition_binds_compatible_observer_epochs() -> None:
    """Current regime claims must span exact compatible observer restarts."""
    report = _load(_REPORT)
    regime = _load(_V49_REGIME)
    decision = report["regime_disposition"]["latest_v49_cross_restart_accuracy"]
    routes = regime["horizons"]["60m"]["by_provider_symbol"]
    eth = routes["range_onset_bidirectional_v1|ETH"]["state_fields"]["primary_regime"]

    assert decision["report"] == str(_V49_REGIME)
    assert decision["sha256"] == file_evidence(_V49_REGIME)["sha256"]
    assert regime["source"]["compatible_run_count"] == 3
    assert regime["source"]["candidate_observations"] == 1605
    assert regime["canonical_source"]["candidate_observations"] == 476
    assert eth["repeated"]["TREND_DOWN"]["directional_accuracy_pct"] == (
        pytest.approx(59.22077922077922)
    )
    assert eth["episode_onsets"]["TREND_DOWN"]["directional_accuracy_pct"] == 0.0
    assert report["regime_disposition"]["automatic_leverage_change"] is False
    assert str(_V49_REGIME) in report["evidence_paths"]


@pytest.mark.evidence
def test_v49_expansion_disposition_reconciles_development_and_parity() -> None:
    """Expansion candidates must retain path failures and signal parity."""
    report = _load(_REPORT)
    candidates = {
        row["symbol"]: row for row in report["expansion_research_disposition"]
    }
    sources = {
        "xyz:MU": (_load(_MU_DIAGNOSTIC), _load(_MU_PARITY)),
        "xyz:SKHX": (_load(_SKHX_DIAGNOSTIC), _load(_SKHX_PARITY)),
    }
    for symbol, (diagnostic, parity) in sources.items():
        candidate = candidates[symbol]
        coverage = parity["coverage"]
        assessment = parity["technical_assessment"]
        parity_path = Path(candidate["prospective_signal_parity_report"])
        assert candidate["historical_path_status"] == "unresolved"
        assert (
            candidate["prospective_signal_decision_bars"] == coverage["decision_bars"]
        )
        assert candidate["prospective_signal_disagreement_bars"] == 0
        assert (
            candidate["prospective_signal_entry_events"]
            == coverage["trade_entry_events"]
        )
        assert (
            candidate["prospective_entry_signal_parity_non_vacuous"]
            == assessment["prospective_entry_signal_parity_non_vacuous"]
        )
        assert (
            candidate["prospective_signal_parity_sha256"]
            == file_evidence(parity_path)["sha256"]
        )
        assert assessment["prospective_signal_source_parity_resolved"] is True
        assert diagnostic["execution_authority"] == "none"
    assert candidates["xyz:MU"]["priority"] == 1
    assert candidates["xyz:SKHX"]["priority"] == 2
    assert candidates["xyz:MU"]["prospective_signal_entry_events"] == 2
    assert candidates["xyz:SKHX"]["prospective_signal_entry_events"] == 0
    assert candidates["xyz:CL"]["stress_net_without_largest_winner_usd"] == (
        pytest.approx(
            _load(_CL_DIAGNOSTIC)["development_economics"]["stress"]["diagnostics"][
                "all"
            ]["net_without_largest_winner_usd"]
        )
    )
    assert (
        candidates["xyz:SILVER"]["unresolved_lifecycle_trades"]
        == (
            _load(_SILVER_DIAGNOSTIC)["technical_path_evidence"]["nominal"]["summary"][
                "unresolved_lifecycle_trades"
            ]
        )
    )
    for symbol, source in (("xyz:MU", _MU_MARKOUTS), ("xyz:CL", _CL_MARKOUTS)):
        markouts = _load(source)
        candidate = candidates[symbol]
        assert (
            candidate["prospective_eligible_onsets"]
            == markouts["source"]["eligible_onset_decisions"]
        )
        assert candidate["prospective_15m_mean_after_friction_bps"] == pytest.approx(
            markouts["markouts"]["horizons"]["15"]["summary"][
                "mean_after_modeled_friction_bps"
            ]
        )
        assert markouts["contract"]["pnl_claimed"] is False
    assert _TRADE_ORACLE_REVIEW.exists()
    assert str(_TRADE_ORACLE_REVIEW) in report["evidence_paths"]
    assert all(row["automatic_roster_change"] is False for row in candidates.values())


@pytest.mark.evidence
def test_v49_exact_observer_execution_disposition_reconciles_sources() -> None:
    """Near-miss claims must bind exact depth, fee, funding, and observer identity."""
    report = _load(_REPORT)
    decision = report["observer_exact_execution_disposition"]

    for key, path in _EXACT_OBSERVER_REPORTS.items():
        source = _load(path)
        side = source["by_side"]["long"]
        expected = decision[key]
        assert expected["resolved"] == side["resolved"]
        assert expected["wins"] == side["wins"]
        assert expected["losses"] == side["losses"]
        assert expected["mean_net_return_bps"] == pytest.approx(
            side["mean_net_return_bps"]
        )
        assert (
            expected["visible_depth_complete_attempts"]
            == (source["entry_depth_diagnostics"]["visible_depth_complete_count"])
        )
        assert source["contract"]["liquidity_rule"] == (
            "entire_notional_visible_within_recorded_depth"
        )
        assert (
            source["source"]["effective_profile_fingerprint"]
            == decision["effective_profile_fingerprint"]
        )
        assert source["execution_authority"] == "none"
        assert str(path) in report["evidence_paths"]
    assert decision["automatic_strategy_change"] is False


@pytest.mark.evidence
def test_v49_observer_regime_interactions_are_route_specific() -> None:
    """Exact entry states must support diagnosis without creating a regime gate."""
    report = _load(_REPORT)
    diagnostic = build_observer_regime_interactions(
        [_load(path) for path in _EXACT_OBSERVER_REPORTS.values()]
    )
    decision = report["observer_regime_interaction_disposition"]
    routes = {
        (row["symbol"], row["blocker"], row["horizon_minutes"]): row
        for row in diagnostic["routes"]
    }
    sol = routes[("SOL", "awaiting_hourly_sma_cross", 15)]
    hype = routes[("HYPE", "canonical_breakout_onset_absent", 15)]

    for key, source in (
        (
            "sol_missing_hourly_cross_opposed_15m",
            sol["by_context_15m_relation"]["opposed"],
        ),
        ("hype_missing_onset_aligned_15m", hype["by_context_15m_relation"]["aligned"]),
    ):
        assert decision[key]["resolved"] == source["resolved"]
        assert decision[key]["total_net_return_bps"] == pytest.approx(
            source["total_net_return_bps"]
        )
        assert decision[key]["net_excluding_largest_winner_bps"] == pytest.approx(
            source["net_excluding_largest_winner_bps"]
        )
    assert decision["automatic_strategy_change"] is False
    assert diagnostic["execution_authority"] == "none"


@pytest.mark.evidence
def test_v49_disposition_records_first_repaired_range_eligible_lifecycle() -> None:
    """The repaired Range route must no longer be described as never eligible."""
    report = _load(_REPORT)
    source = _load(_SOL_ELIGIBLE_FORWARD)
    decision = report["observer_eligible_lifecycle_disposition"]
    attempt = source["latest_attempts"][0]

    assert decision["eligible_signals"] == source["summary"]["eligible_signals"] == 1
    assert decision["strategy_id"] == attempt["strategy_id"]
    assert decision["symbol"] == attempt["symbol"] == "SOL"
    assert decision["side"] == attempt["side"] == "short"
    assert decision["status"] == attempt["status"] == "exit_pending"
    assert decision["initial_snapshot_net_after_funding_bps"] == pytest.approx(
        attempt["current_estimated_net_after_funding_bps"]
    )
    assert source["contract"]["stop_bps"] == 80.0
    assert source["contract"]["maximum_hold_minutes"] == 2_880
    assert source["contract"]["execution_authority"] == "none"
    assert str(_SOL_ELIGIBLE_FORWARD) in report["evidence_paths"]


@pytest.mark.evidence
def test_v49_disposition_hash_binds_the_pending_sol_profit_lock_snapshot() -> None:
    """The newer path must augment rather than rewrite the first frozen snapshot."""
    report = _load(_REPORT)
    source = _load(_SOL_PROFIT_LOCK_FORWARD)
    decision = report["observer_eligible_lifecycle_disposition"]
    attempt = source["latest_attempts"][0]
    exact = source["exact_visible_depth_lifecycle"]["latest_attempts"][0]

    assert decision["profit_lock_forward_snapshot"] == str(_SOL_PROFIT_LOCK_FORWARD)
    assert (
        decision["profit_lock_forward_snapshot_sha256"]
        == file_evidence(_SOL_PROFIT_LOCK_FORWARD)["sha256"]
    )
    assert (
        decision["profit_lock_forward_snapshot_observed_candles"]
        == attempt["observed_candles"]
    )
    assert decision["profit_lock_forward_snapshot_mfe_bps"] == pytest.approx(
        attempt["mfe_bps"]
    )
    assert decision[
        "profit_lock_forward_snapshot_exact_visible_depth_net_after_funding_bps"
    ] == pytest.approx(exact["current_net_return_bps"])
    assert source["profit_lock_challenger"]["contract"]["execution_authority"] == (
        "none"
    )


@pytest.mark.evidence
def test_v49_disposition_hash_binds_cross_restart_profit_lock_evidence() -> None:
    """Latest evidence must extend compatible epochs without rewriting v1."""
    report = _load(_REPORT)
    source = _load(_SOL_PROFIT_LOCK_CONTINUATION)
    decision = report["observer_eligible_lifecycle_disposition"]
    attempt = source["latest_attempts"][0]
    exact = source["exact_visible_depth_lifecycle"]["latest_attempts"][0]
    policies = source["profit_lock_challenger"]["latest_results"][0]["policies"]

    assert decision["profit_lock_forward_continuation_snapshot"] == str(
        _SOL_PROFIT_LOCK_CONTINUATION
    )
    assert (
        decision["profit_lock_forward_continuation_snapshot_sha256"]
        == (file_evidence(_SOL_PROFIT_LOCK_CONTINUATION)["sha256"])
    )
    assert source["contract"]["compatible_run_count"] == 3
    assert attempt["observed_candles"] == 210
    assert exact["current_net_return_bps"] == pytest.approx(12.767684327315154)
    assert all(
        row["status"] == "triggered_before_current_boundary"
        and row["counterfactual_economics"][
            "estimated_minus_current_exit_net_excluding_funding_usd"
        ]
        > 0.0
        for row in policies.values()
    )
    assert str(_SOL_PROFIT_LOCK_CONTINUATION) in report["evidence_paths"]
