"""Exact identity contracts for the v53 continuous-improvement feed."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_first_event_capture import validate_baseline

_ROOT = Path(__file__).parents[1]
_CONFIG = _ROOT / "configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml"
_OVERRIDES = _ROOT / "configs/research/cohort_improvement_decision_overrides_v53.json"
_SCRIPT = _ROOT / "scripts/cohort_improvement_monitor.py"
_ROUTES = {
    "hulk_expansion_short_robust_v3|BTC",
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
}


def test_v53_override_is_exact_report_only_and_marks_repair_deployed() -> None:
    """The improvement feed must describe v53 rather than stale v51/v52 state."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    assert payload["source_profile_id"] == config.profile_id
    assert payload["source_profile_fingerprint"] == config.profile_fingerprint
    assert set(payload["routes"]) == _ROUTES
    assert payload["change_proposals"] == []
    assert payload["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    assert (
        decisions["v53-hype-maximum-hold-evidence-freshness-repair-v1"]["status"]
        == "accepted"
    )


@pytest.mark.evidence
def test_v53_override_evidence_is_immutable_and_loadable() -> None:
    """Every declared v53 source must reconcile before a digest is built."""
    spec = spec_from_file_location("v53_improvement_monitor", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load cohort improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    payload, raw = module._load_decision_overrides(_OVERRIDES)

    assert raw == _OVERRIDES.read_bytes()
    assert payload["active_hypotheses"][0]["hypothesis_id"] == (
        "v53-first-eligible-lifecycle-audit-v1"
    )
    assert len(payload["evidence"]) >= 5


def test_v53_override_closes_rejected_xyz100_krown_hypothesis() -> None:
    """The monitor must retain the frozen XYZ100 failure and reopen condition."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["V53_XYZ100_KROWN_TREND_RESUMPTION_DEVELOPMENT_V1"]
    assert decision["status"] == "rejected"
    assert decision["route"] == "krown_trend_resumption|xyz:XYZ100"
    assert decision["decision_source"] == (
        "docs/research-journal/v53-xyz100-krown-trend-resumption-development-v1.json"
    )
    assert (
        "materially different preregistered signal thesis"
        in decision["reopen_condition"]
    )


def test_v53_override_uses_resolved_hype_nearmiss_stop_path() -> None:
    """The digest must supersede the pre-stop HYPE near-miss revision."""
    payload = json.loads(_OVERRIDES.read_text())
    paths = {row["path"] for row in payload["evidence"]}
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    assert (
        "../../docs/research-journal/v53-hype-first-canonical-onset-nearmiss-v2.json"
    ) in paths
    assert (
        "../../docs/research-journal/v53-hype-first-canonical-onset-nearmiss-v1.json"
    ) not in paths
    decision = decisions["v53-hype-first-canonical-onset-nearmiss-v2"]
    assert decision["status"] == "rejected"
    assert decision["decision_source"] == (
        "docs/research-journal/v53-hype-first-canonical-onset-nearmiss-v2.json"
    )


def test_v53_override_uses_extended_hype_onset_rejection() -> None:
    """The digest must retain the mature primary-horizon onset rejection."""
    payload = json.loads(_OVERRIDES.read_text())
    paths = {row["path"] for row in payload["evidence"]}
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    revised = (
        "../../docs/research-journal/"
        "v53-hype-canonical-onset-one-blocker-extended-window-v2.json"
    )
    stale = (
        "../../docs/research-journal/"
        "v53-hype-canonical-onset-one-blocker-first-window-v1.json"
    )
    assert revised in paths
    assert stale not in paths
    decision = decisions["v53-hype-canonical-onset-one-blocker-first-window-v1"]
    assert decision["status"] == "rejected"
    assert decision["decision_source"] == revised.removeprefix("../../")
    assert (
        "twenty-two independent five-minute paths"
        in decision["decision_reason"].lower()
    )
    assert decision["closed_live_diagnostic_blockers"] == [
        "canonical_breakout_onset_absent"
    ]


def test_v53_override_uses_adverse_btc_sweep_revision() -> None:
    """The digest must not keep the superseded v52 BTC-sweep assessment."""
    payload = json.loads(_OVERRIDES.read_text())
    paths = {row["path"] for row in payload["evidence"]}
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    assert (
        "../../docs/research-journal/v53-btc-sweep-primary-trigger-relaxation-v2.json"
        in paths
    )
    decision = decisions["v52-btc-sweep-primary-trigger-relaxation-v1"]
    assert decision["status"] == "deferred"
    assert decision["decision_source"] == (
        "docs/research-journal/v53-btc-sweep-primary-trigger-relaxation-v2.json"
    )
    assert "four cross-run exact-route episodes" in decision["decision_reason"].lower()


def test_v53_override_uses_fixed_cap_hulk_diagnosis() -> None:
    """The central ledger must not reuse risk-normalized Hulk robustness claims."""
    payload = json.loads(_OVERRIDES.read_text())
    paths = {row["path"] for row in payload["evidence"]}
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    route = payload["routes"]["hulk_expansion_short_robust_v3|BTC"]

    journal_path = (
        "../../docs/research-journal/v53-btc-hulk-fixed-cap-evidence-parity-v1.json"
    )
    assert journal_path in paths
    assert route["decision_source"] == journal_path.removeprefix("../../")
    assert "fixed-cap" in route["historical_assessment"]
    decision = decisions["v53-btc-hulk-fixed-cap-evidence-parity-v1"]
    assert decision["status"] == "accepted"
    assert decision["decision_source"] == journal_path.removeprefix("../../")
    assert decision["proposed_live_change"] is None


def test_v53_override_tracks_latest_eth_prefix_without_relaxation() -> None:
    """The central ledger must retain the latest isolated ETH prefix result."""
    payload = json.loads(_OVERRIDES.read_text())
    paths = {row["path"] for row in payload["evidence"]}
    active = {row["hypothesis_id"]: row for row in payload["active_hypotheses"]}

    assert (
        "../../docs/research-journal/eth-breakout-precompression-pullback-v13.json"
        in paths
    )
    latest = (
        "../../docs/research-journal/v53-eth-pullback-forward-prefix-result-v1.json"
    )
    assert latest in paths
    hypothesis = active["eth-remove-canonical-breakout-onset-forward-v1"]
    assert hypothesis["status"] == "being_tested"
    assert hypothesis["route"] == "research_only|ETH"
    assert hypothesis["decision_source"] == (
        "docs/research-journal/v53-eth-pullback-forward-prefix-result-v1.json"
    )
    assert hypothesis["execution_effect"] == "report_only"
    assert hypothesis["automatic_live_change"] is False

    journal = json.loads((_ROOT / hypothesis["decision_source"]).read_text())
    assert journal["state"] == "being_tested_no_live_change_supported"
    assert journal["scope"]["eligible_evaluations"] == 0
    assert journal["scope"]["observed_evaluations_by_side"] == {
        "long": 368,
        "short": 0,
    }
    result = journal["independent_readiness_paths_after_estimated_friction"]["5m"]
    assert result["mean_excluding_largest_bps"] == pytest.approx(-12.775535395194666)
    assert journal["approval_requested"] is False


def test_v53_override_tracks_active_mu_transport_window() -> None:
    """The external diversification experiment must remain in the live ledger."""
    payload = json.loads(_OVERRIDES.read_text())
    active = {row["hypothesis_id"]: row for row in payload["active_hypotheses"]}
    hypothesis = active["MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V2"]

    assert hypothesis["status"] == "being_tested"
    assert hypothesis["route"] == "research_only|xyz:MU"
    assert hypothesis["execution_effect"] == "report_only"
    assert hypothesis["automatic_live_change"] is False
    preregistration = _ROOT / hypothesis["decision_source"]
    journal = json.loads(preregistration.read_text())
    assert journal["scope"]["expected_decisions"] == 96
    assert journal["contract"]["no_parameter_retuning_during_window"] is True
    assert journal["economic_boundary"]["live_change_proposal"] is None
    repair = json.loads((_ROOT / hypothesis["repair_source"]).read_text())
    assert repair["incident"]["first_past_due_missing_decision_utc"] == (
        "2026-08-17T21:00:00Z"
    )
    assert repair["window_disposition"]["replacement_window_started"] is False
    assert repair["recommendation"]["proposed_live_change"] is None


def test_v53_override_closes_index_opening_range_development() -> None:
    """The central ledger must retain the frozen index-family rejection."""
    payload = json.loads(_OVERRIDES.read_text())
    paths = {row["path"] for row in payload["evidence"]}
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    active = {row["hypothesis_id"] for row in payload["active_hypotheses"]}
    hypothesis_id = "V53_SP500_SPCX_OPENING_RANGE_BREAKOUT_DEVELOPMENT_V1"

    assert hypothesis_id not in active
    decision = decisions[hypothesis_id]
    assert decision["status"] == "rejected"
    assert decision["proposed_live_change"] is None
    assert decision["decision_source"] == (
        "docs/research-journal/"
        "v53-sp500-spcx-opening-range-breakout-development-result-v1.json"
    )
    expected = {
        "../../docs/research-journal/"
        "v53-sp500-spcx-opening-range-breakout-development-result-v1.json",
        "../../data/logs/research/"
        "xyz_sp500_opening_range_breakout_development_20260817_v1.json",
        "../../data/logs/research/"
        "xyz_spcx_opening_range_breakout_development_20260817_v1.json",
    }
    assert expected <= paths


def test_v53_override_records_cash_open_gap_reversal_disposition() -> None:
    """SP500 rejection and SPCX technical deferral must remain distinct."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    paths = {row["path"] for row in payload["evidence"]}
    hypothesis_id = "V53_SP500_SPCX_CASH_OPEN_GAP_REVERSAL_V1"

    decision = decisions[hypothesis_id]
    assert decision["status"] == "deferred"
    assert decision["proposed_live_change"] is None
    journal = json.loads((_ROOT / decision["decision_source"]).read_text())
    assert journal["results"]["xyz:SP500"]["stress_net_usd"] < 0
    spcx = journal["results"]["xyz:SPCX"]
    assert spcx["stress_net_usd"] > 0
    assert spcx["stress_net_without_largest_winner_usd"] > 0
    assert spcx["unresolved_lifecycle_trades"] == 11
    assert journal["validation_accessed"] is False
    assert journal["holdout_accessed"] is False
    expected = {
        f"../../{decision['decision_source']}",
        "../../data/logs/research/xyz_sp500_cash_open_gap_reversal_development_20260817_v1.json",
        "../../data/logs/research/xyz_spcx_cash_open_gap_reversal_development_20260817_v1.json",
    }
    assert expected <= paths


def test_v53_override_tracks_exact_spcx_cash_open_prospective_window() -> None:
    """Keep the unchanged SPCX route active only as prospective research."""
    payload = json.loads(_OVERRIDES.read_text())
    active = {row["hypothesis_id"]: row for row in payload["active_hypotheses"]}
    paths = {row["path"] for row in payload["evidence"]}
    row = active["V53_SPCX_CASH_OPEN_PROSPECTIVE_V1"]

    assert row["status"] == "being_tested"
    assert row["execution_effect"] == "report_only"
    assert row["automatic_live_change"] is False
    assert row["observed_entry_count"] == 0
    assert row["scorable_cash_open_decisions"] == 1
    assert {
        "../../data/logs/research/xyz_spcx_prospective_path_audit_20260817_v3.json",
        "../../data/logs/research/xyz_spcx_cash_open_prospective_20260817_v1.json",
        "../../docs/research-journal/v53-spcx-cash-open-prospective-prefix-v1.json",
    } <= paths


def test_v53_override_rejects_failed_mu_cash_open_transfer_without_oos_access() -> None:
    """Preserve the frozen MU failure without tuning or opening OOS."""
    payload = json.loads(_OVERRIDES.read_text())
    active = {row["hypothesis_id"] for row in payload["active_hypotheses"]}
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    hypothesis_id = "V53_MU_CASH_OPEN_GAP_TRANSFER_V1"

    assert hypothesis_id not in active
    decision = decisions[hypothesis_id]
    assert decision["status"] == "rejected"
    preregistration = json.loads(
        (_ROOT / decision["preregistration_source"]).read_text()
    )
    assert preregistration["state"] == "preregistered_before_pnl"
    assert preregistration["portfolio_contract"]["notional_usd_per_position"] == 2000.0
    assert preregistration["strategy_contract"]["gap_threshold_bps"] == 20.0
    result = json.loads((_ROOT / decision["decision_source"]).read_text())
    assert result["validation_accessed"] is False
    assert result["holdout_accessed"] is False
    assert result["result"]["stress_net_usd"] < 0
    assert decision["proposed_live_change"] is None


def test_v53_override_retains_superseded_and_deferred_research_boundaries() -> None:
    """Technical failures and deliberate pauses must not silently reopen."""
    payload = json.loads(_OVERRIDES.read_text())
    paths = {row["path"] for row in payload["evidence"]}
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    first_window = decisions["MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V1"]
    assert first_window["status"] == "superseded"
    assert first_window["superseded_by"] == (
        "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V2"
    )
    brent = decisions["v53-brentoil-candle-revision-technical-pause-v1"]
    assert brent["status"] == "deferred"
    assert brent["proposed_live_change"] is None
    selectivity = decisions["V53_FIRST_14H_SELECTIVITY_VS_MISSED_OPPORTUNITY_V1"]
    assert selectivity["status"] == "accepted"
    assert selectivity["proposed_live_change"] is None
    expected = {
        "../../docs/research-journal/"
        "v53-mu-transport-window-final-result-and-observer-repair-v1.json",
        "../../docs/research-journal/"
        "v53-mu-observer-repair-first-prospective-boundary-v1.json",
        "../../docs/research-journal/"
        "v53-brentoil-candle-revision-technical-pause-v1.json",
        "../../docs/research-journal/"
        "v53-first-14h-readiness-and-missed-opportunity-audit-v1.json",
    }
    assert expected <= paths


def test_v53_override_uses_corrected_top_liquidity_disposition() -> None:
    """The opportunity queue must not retain the failed MU-v1 cutoff."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    paths = {row["path"] for row in payload["evidence"]}

    prior = decisions["V53_HIP3_TOP10_LIQUIDITY_SCREEN_V1"]
    assert prior["status"] == "superseded"
    assert prior["superseded_by"] == "V53_HIP3_TOP10_LIQUIDITY_SCREEN_V2"
    current = decisions["V53_HIP3_TOP10_LIQUIDITY_SCREEN_V2"]
    assert current["status"] == "accepted"
    assert current["proposed_live_change"] is None
    source = _ROOT / current["decision_source"]
    journal = json.loads(source.read_text())
    assert journal["corrected_mu_window"]["first_decision_utc"] == (
        "2026-08-17T20:00:00Z"
    )
    assert journal["corrected_mu_window"]["end_exclusive_utc"] == (
        "2026-08-18T20:00:00Z"
    )
    assert journal["corrected_mu_window"]["expected_decisions"] == 96
    assert journal["live_change_proposed"] is False
    assert f"../../{current['decision_source']}" in paths


def test_v53_override_closes_hype_side_coverage_anomaly() -> None:
    """A long-only window must distinguish regime persistence from a side bug."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    paths = {row["path"] for row in payload["evidence"]}
    decision = decisions["V53_HYPE_DIRECTIONAL_SIDE_COVERAGE_AUDIT_V1"]

    assert decision["status"] == "accepted"
    assert decision["proposed_live_change"] is None
    journal = json.loads((_ROOT / decision["decision_source"]).read_text())
    assert journal["source_evaluations_by_side"] == {"long": 935, "short": 0}
    assert journal["breakout_side_observations"] == {
        "long": 5,
        "short": 5,
        "unavailable": 925,
    }
    assert journal["fresh_breakout_onsets"] == 2
    assert journal["missed_eligible_entries"] == 0
    assert journal["live_change_proposed"] is False
    assert f"../../{decision['decision_source']}" in paths


def test_v53_override_records_payoff_and_growth_capacity() -> None:
    """The ledger must distinguish meaningful risk from unproven expectancy."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    paths = {row["path"] for row in payload["evidence"]}
    decision = decisions["V53_CONFIGURED_PAYOFF_GROWTH_CAPACITY_V2"]

    assert decision["status"] == "accepted"
    assert decision["proposed_live_change"] is None
    journal = json.loads((_ROOT / decision["decision_source"]).read_text())
    assert journal["revision_number"] == 2
    assert journal["configured_exposure"]["actual_position_capacity"] == 2
    assert journal["configured_exposure"]["simultaneous_p99_loss_usd"] > 90
    assert journal["route_payoffs"]["btc_sweep"]["breakeven_win_rate"] > 0.64
    assert journal["route_payoffs"]["hype"]["fixed_target_bps"] is None
    assert journal["recommendation"]["proposed_live_change"] is None
    assert f"../../{decision['decision_source']}" in paths


def test_v53_override_closes_hype_l2_ridge_growth_candidate() -> None:
    """The retired-route Ridge annotation must not masquerade as new cadence."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    paths = {row["path"] for row in payload["evidence"]}
    decision = decisions["V53_HYPE_L2_RIDGE_PROSPECTIVE_CLOSURE_V1"]

    assert decision["status"] == "rejected"
    assert decision["proposed_live_change"] is None
    journal = json.loads((_ROOT / decision["decision_source"]).read_text())
    assert journal["prospective_outcomes"]["resolved"] == 4
    assert journal["prospective_outcomes"]["wins"] == 0
    assert journal["prospective_outcomes"]["net_return_bps"] < -292
    assert journal["prospective_outcomes"]["directional_sign_agreement_rate"] == 0
    assert journal["novelty_assessment"]["independent_entry_mechanism"] is False
    assert journal["novelty_assessment"]["compatible_with_v53_hype_route"] is False
    assert journal["recommendation"]["proposed_live_change"] is None
    assert f"../../{decision['decision_source']}" in paths


def test_v53_override_defers_adverse_mu_lifecycle_candidate() -> None:
    """MU must remain report-only while results depend on one large winner."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    paths = {row["path"] for row in payload["evidence"]}
    decision = decisions["V53_MU_PROSPECTIVE_LIFECYCLE_UPDATE_V1"]

    assert decision["status"] == "deferred"
    assert decision["proposed_live_change"] is None
    journal = json.loads((_ROOT / decision["decision_source"]).read_text())
    result = journal["prospective_result"]
    assert result["completed_lifecycles"] == 8
    assert result["wins"] == 2
    assert result["losses"] == 6
    assert result["nominal_net_usd"] > 0
    assert result["nominal_net_excluding_largest_winner_usd"] < 0
    assert result["stress_net_excluding_largest_winner_usd"] < 0
    assert result["short_wins"] == 0
    assert journal["recommendation"]["proposed_live_change"] is None
    assert f"../../{decision['decision_source']}" in paths


def test_v53_override_freezes_verified_hype_exit_runtime_contract() -> None:
    """The digest must distinguish router exits from provider recipe exits."""
    payload = json.loads(_OVERRIDES.read_text())
    paths = {row["path"] for row in payload["evidence"]}
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    route = payload["routes"][
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
    ]
    journal_path = (
        "../../docs/research-journal/"
        "v53-hype-exit-runtime-contract-verification-v1.json"
    )

    assert journal_path in paths
    assert route["decision_source"] == journal_path.removeprefix("../../")
    assert journal_path.removeprefix("../../") in route["supporting_evidence"]
    decision = decisions["V53_HYPE_EXIT_RUNTIME_PARITY_V1"]
    assert decision["status"] == "accepted"
    assert decision["proposed_live_change"] is None
    assert decision["decision_source"] == journal_path.removeprefix("../../")


@pytest.mark.evidence
def test_v53_first_event_baseline_is_an_exact_zero_counter_live_audit() -> None:
    """The watcher baseline must be diffable, not deployment acceptance metadata."""
    payload = json.loads(_OVERRIDES.read_text())
    hypothesis = payload["active_hypotheses"][0]
    baseline = _ROOT / hypothesis["evidence_baseline"]
    identity = {
        "run_id": hypothesis["baseline_identity"]["run_id"],
        "profile_id": hypothesis["baseline_identity"]["profile_id"],
        "profile_fingerprint": hypothesis["baseline_identity"]["profile_fingerprint"],
    }

    validate_baseline(baseline, identity)
    audit = json.loads(baseline.read_text())
    counters = audit["routing"]["entry_age_diagnostics"]
    assert counters["eligible_evaluations"] == 0
    assert audit["routing"]["strategy_intents"] == 0
    assert audit["routing"]["actions"] == 0
    assert audit["routing"]["withheld"] == 0
    assert audit["execution"]["fills"] == 0
    assert audit["execution"]["open_lifecycles"] == 0
    assert audit["execution"]["closed_trades"] == 0
