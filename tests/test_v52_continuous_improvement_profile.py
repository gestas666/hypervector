"""Exact identity contracts for the v52 continuous-improvement feed."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from hypervector.data.research_database import ResearchDatabase

_ROOT = Path(__file__).parents[1]
_OVERRIDES = _ROOT / "configs/research/cohort_improvement_decision_overrides_v52.json"
_SCRIPT = _ROOT / "scripts/cohort_improvement_monitor.py"
_CADENCE_THRESHOLDS = (
    _ROOT / "docs/research-journal/v52-empirical-interarrival-review-thresholds-v1.json"
)
_DIRECTION_SWEEP_JOURNAL = (
    _ROOT
    / "docs/research-journal/v52-one-sided-readiness-and-btc-sweep-near-miss-v1.json"
)
_HYPE_ONSET_JOURNAL = (
    _ROOT / "docs/research-journal/v52-hype-canonical-onset-relaxation-forward-v1.json"
)
_HYPE_ALIGNMENT_JOURNAL = (
    _ROOT / "docs/research-journal/v52-hype-noncompression-alignment-relaxation-v1.json"
)
_HYPE_ALIGNMENT_HISTORY = tuple(
    _ROOT / f"docs/research-journal/hype-breakout-direction-alignment-v{revision}.json"
    for revision in range(1, 6)
)
_HYPE_SIDE_ALIGNMENT_JOURNAL = (
    _ROOT / "docs/research-journal/v52-hype-breakout-side-alignment-relaxation-v1.json"
)
_PROFILE = "multi_asset_growth_first_5000_evidence_bound_successor_v52"
_FINGERPRINT = "662d28b352cfc4f09e08c71ee67c8f044421483f2932539b09ea082b5e4f27f7"
_ROUTES = {
    "hulk_expansion_short_robust_v3|BTC",
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
}
_FRESHNESS_PROPOSAL = "v52-hype-maximum-hold-evidence-freshness-v1"


def _assert_approved_freshness_proposal(payload: dict[str, object]) -> None:
    proposals = payload["change_proposals"]
    assert isinstance(proposals, list)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert isinstance(proposal, dict)
    assert proposal["proposal_id"] == _FRESHNESS_PROPOSAL
    assert proposal["approval_status"] == "approved_waiting_flat_boundary"
    assert proposal["execution_effect"] == "approved_not_deployed"
    assert proposal["automatic_live_change"] is False


def test_v52_override_binds_only_the_live_successor_routes() -> None:
    """Stale v51 routes cannot enter the exact v52 improvement queue."""
    payload = json.loads(_OVERRIDES.read_text())

    assert payload["source_profile_id"] == _PROFILE
    assert payload["source_profile_fingerprint"] == _FINGERPRINT
    assert set(payload["routes"]) == _ROUTES
    _assert_approved_freshness_proposal(payload)
    assert payload["contract"]["execution_authority"] == "none"
    assert payload["contract"]["runtime_strategy_changed"] is False


def test_v52_override_evidence_hashes_reconcile() -> None:
    """Every frozen v52 research source must match its declared bytes and hash."""
    spec = spec_from_file_location("v52_improvement_monitor", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load cohort improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    payload, raw = module._load_decision_overrides(_OVERRIDES)

    assert raw == _OVERRIDES.read_bytes()
    assert len(payload["evidence"]) == 31
    evidence_paths = {row["path"] for row in payload["evidence"]}
    assert (
        "../../docs/research-journal/v52-tui-checkpoint-readiness-repair-v1.json"
        in evidence_paths
    )
    assert (
        "../../data/logs/research/bidirectional_cohort/"
        "v52_live_prefix_delta_20260817T0105Z_0211Z.json"
    ) in evidence_paths
    assert (
        "../../docs/research-journal/v52-hype-maximum-hold-evidence-freshness-v1.json"
    ) in evidence_paths


def test_v52_override_closes_rejected_cross_asset_family() -> None:
    """The active ledger must not recycle the exhausted cross-asset search."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["cross_asset_residual_and_impulse_family_v1"]
    assert decision["status"] == "rejected"
    assert decision["experiment"] == (
        "residual_pair_exit_surface_and_leader_follower_impulse"
    )
    assert "separately versioned causal mechanism" in decision["reopen_condition"]


def test_v52_override_records_availability_causal_repair() -> None:
    """The closed hypothesis ledger must retain the repaired markout contract."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-report-only-signal-availability-causality-v1"]
    assert decision["status"] == "accepted"
    assert decision["experiment"] == "availability_causal_forward_paths"
    assert decision["decision_source"].endswith(
        "v52-first-hour-route-readiness-and-missed-opportunity-v2.json"
    )


def test_v52_override_records_quiet_window_cadence_diagnosis() -> None:
    """A short quiet window must not reopen rejected entry relaxations."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-opening-quiet-window-cadence-v1"]
    assert decision["status"] == "accepted"
    assert decision["experiment"] == "opening_quiet_window_cadence_consistency"
    assert decision["decision_source"].endswith(
        "v52-opening-quiet-window-cadence-v1.json"
    )


def test_v52_override_records_empirical_cadence_review_thresholds() -> None:
    """Prospective cadence reviews must use frozen empirical thresholds."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-empirical-cadence-review-thresholds-v1"]
    assert decision["status"] == "accepted"
    assert decision["experiment"] == "empirical_interarrival_review_schedule"
    assert decision["decision_source"].endswith(
        "v52-empirical-interarrival-review-thresholds-v1.json"
    )


def test_v52_empirical_cadence_binds_hype_signal_sidecar() -> None:
    """HYPE interarrival evidence must bind the exact aligned trade rows."""
    payload = json.loads(_CADENCE_THRESHOLDS.read_text())
    evidence = {row["path"]: row for row in payload["source_evidence"]}
    sidecar = evidence[
        "data/logs/research/hype_compression_breakout_challenger_20260816_"
        "v6_alignment/alignment_development_trades.parquet"
    ]

    assert sidecar["bytes"] == 25432
    assert sidecar["sha256"] == (
        "85e83cd5369b415fc8926ba0d645e157d2c07e7de611f7c3151364a111809c33"
    )


def test_v52_override_records_opening_regime_fit_diagnosis() -> None:
    """The ledger must distinguish regime-compatible silence from defects."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-opening-regime-fit-diagnosis-v1"]
    assert decision["status"] == "accepted"
    assert decision["experiment"] == "opening_route_regime_fit_diagnosis"
    assert decision["decision_source"].endswith(
        "v52-opening-regime-fit-diagnosis-v1.json"
    )


def test_v52_override_records_hype_side_and_exit_contract() -> None:
    """The ledger must retain the verified bidirectional HYPE exit behavior."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-hype-side-and-opposite-exit-contract-v1"]
    assert decision["status"] == "accepted"
    assert decision["experiment"] == (
        "bidirectional_side_and_opposite_signal_exit_contract"
    )
    assert decision["decision_source"].endswith(
        "v52-hype-side-and-opposite-exit-contract-v1.json"
    )


def test_v52_override_rejects_aligned_symmetric_fixed_targets() -> None:
    """The monitor must not reopen the exact fixed-target grid without new evidence."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-hype-aligned-fixed-target-sensitivity"]
    assert decision["status"] == "rejected"
    assert decision["experiment"] == "symmetric_fixed_target_40_500_bps"
    assert decision["route"] == (
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
    )
    assert decision["decision_source"].endswith(
        "v52-hype-aligned-fixed-target-sensitivity-v2.json"
    )


def test_v52_override_rejects_current_route_onset_relaxation() -> None:
    """The ledger must retain the threshold-complete v52 onset decision."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-hype-remove-canonical-breakout-onset-v1"]
    assert decision["status"] == "rejected"
    assert decision["experiment"] == "remove_canonical_breakout_onset"
    assert decision["route"] == (
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
    )
    assert decision["decision_source"] == str(_HYPE_ONSET_JOURNAL.relative_to(_ROOT))
    assert "20 independent same-side paths" in decision["reopen_condition"]


def test_v52_override_rejects_noncompression_alignment_reopen() -> None:
    """One mixed forward path cannot reopen the broad aligned-only arm."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-hype-noncompression-alignment-relaxation"]
    assert decision["status"] == "rejected"
    assert decision["experiment"] == "remove_compression_and_pullback_prerequisites"
    assert decision["route"] == (
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
    )
    assert decision["decision_source"] == str(
        _HYPE_ALIGNMENT_JOURNAL.relative_to(_ROOT)
    )
    assert "predeclared independent same-blocker sample" in decision["reopen_condition"]


def test_v52_alignment_decision_starts_a_distinct_research_chain(
    tmp_path: Path,
) -> None:
    """The v52 route cannot mutate the identity of the older onset chain."""
    database = ResearchDatabase(tmp_path / "research.duckdb")
    for record in _HYPE_ALIGNMENT_HISTORY:
        database.append_portfolio_research_revision(record)

    appended = database.append_portfolio_research_revision(_HYPE_ALIGNMENT_JOURNAL)
    older = database.portfolio_research_history("hype-breakout-direction-alignment")
    current = database.portfolio_research_history(
        "v52-hype-noncompression-alignment-relaxation"
    )

    assert appended.inserted is True
    assert len(older["revisions"]) == 5
    assert [row["revision_number"] for row in current["revisions"]] == [1]


def test_v52_override_rejects_breakout_side_alignment_relaxation() -> None:
    """One mixed one-blocker path cannot remove the active side alignment."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-hype-breakout-side-alignment-relaxation"]
    assert decision["status"] == "rejected"
    assert decision["experiment"] == "remove_breakout_side_alignment_requirement"
    assert decision["decision_source"] == str(
        _HYPE_SIDE_ALIGNMENT_JOURNAL.relative_to(_ROOT)
    )
    assert "20 independent exact one-blocker episodes" in decision["reopen_condition"]


def test_v52_side_alignment_decision_is_appendable(tmp_path: Path) -> None:
    """The exact v52 alignment decision must form a valid report-only chain."""
    database = ResearchDatabase(tmp_path / "research.duckdb")

    appended = database.append_portfolio_research_revision(_HYPE_SIDE_ALIGNMENT_JOURNAL)
    history = database.portfolio_research_history(
        "v52-hype-breakout-side-alignment-relaxation"
    )

    assert appended.inserted is True
    assert history["execution_authority"] == "none"
    assert history["revisions"][0]["status"] == "reject"


def test_v52_override_accepts_one_sided_direction_attribution_repair() -> None:
    """Configured one-sided readiness must be retained as a technical repair."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-report-only-one-sided-direction-attribution-v1"]
    assert decision["status"] == "accepted"
    assert decision["experiment"] == "configuration_bound_direction_attribution"
    assert decision["decision_source"] == str(
        _DIRECTION_SWEEP_JOURNAL.relative_to(_ROOT)
    )


def test_v52_override_defers_btc_sweep_trigger_relaxation() -> None:
    """Two non-robust near misses cannot authorize removing the sweep trigger."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    decision = decisions["v52-btc-sweep-primary-trigger-relaxation-v1"]
    assert decision["status"] == "deferred"
    assert decision["experiment"] == "remove_sweep_below_prior_low"
    assert decision["decision_source"] == str(
        _DIRECTION_SWEEP_JOURNAL.relative_to(_ROOT)
    )
    assert "12 independent one-blocker episodes" in decision["reopen_condition"]


def test_v52_direction_and_sweep_journal_is_report_only() -> None:
    """The bounded evidence record cannot mutate the active strategy."""
    journal = json.loads(_DIRECTION_SWEEP_JOURNAL.read_text())

    assert journal["execution_authority"] == "none"
    assert journal["automatic_promotion"] is False
    assert journal["runtime_strategy_changed"] is False
    assert journal["one_sided_direction_attribution"]["no_direction_after"] == 0
    near_miss = journal["btc_sweep_primary_trigger_near_miss"]
    assert near_miss["independent_episodes"] == 2
    assert near_miss["decision"] == "defer_trigger_relaxation"


def test_v52_override_tracks_first_eligible_lifecycle_audit() -> None:
    """The moving research loop must retain its immutable pre-event baseline."""
    payload = json.loads(_OVERRIDES.read_text())
    active = {row["hypothesis_id"]: row for row in payload["active_hypotheses"]}

    hypothesis = active["v52-first-eligible-lifecycle-audit-v1"]
    assert hypothesis["status"] == "being_tested"
    assert hypothesis["experiment"] == "first_eligible_v52_intent_and_lifecycle_audit"
    journal = json.loads((_ROOT / hypothesis["decision_source"]).read_text())
    baseline = _ROOT / hypothesis["evidence_baseline"]
    assert journal["schema_version"] == "v52_first_eligible_lifecycle_audit_baseline_v2"
    assert journal["baseline_identity"] == hypothesis["baseline_identity"]
    assert journal["baseline_identity"]["profile_id"] == _PROFILE
    assert journal["baseline_identity"]["profile_fingerprint"] == _FINGERPRINT
    assert journal["baseline_evidence"] == {
        "path": hypothesis["evidence_baseline"],
        "bytes": baseline.stat().st_size,
        "sha256": sha256(baseline.read_bytes()).hexdigest(),
    }
    assert hypothesis["baseline_counters"] == {
        "eligible_evaluations": 0,
        "strategy_intents": 0,
        "actions": 0,
        "withheld": 0,
        "fills": 0,
        "open_lifecycles": 0,
        "closed_trades": 0,
    }


def test_v52_override_closes_failed_higher_cadence_challengers() -> None:
    """Rejected low-timeframe families cannot silently re-enter the queue."""
    payload = json.loads(_OVERRIDES.read_text(encoding="utf-8"))
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    expected = {
        "hypertrader-impulse-ml-v1": "rejected",
        "venue-native-1m-orderflow-impulse-v1": "rejected",
        "five-minute-liquidity-sweep-reclaim-v1": "rejected",
        "btc-five-minute-l2-expected-return-v2": "rejected",
        "multi-asset-low-timeframe-matrix-v1": "rejected",
        "hype-five-minute-not-breakout-v1": "rejected",
        "sol-hourly-cross-relaxed-route-native-v1": "rejected",
        "oi-forced-deleveraging-exhaustion-v2": "rejected",
        "hype-breakout-retest-fade-v1": "rejected",
        "btc-source-follow-unchanged-v1": "rejected",
    }
    for identity, status in expected.items():
        assert decisions[identity]["status"] == status
        assert decisions[identity]["decision_source"].endswith(
            "higher-cadence-crypto-challenger-disposition-v1.json"
        )
    _assert_approved_freshness_proposal(payload)


def test_v52_override_records_tui_checkpoint_readiness_repair() -> None:
    """The accepted cockpit repair remains visible to continuous research."""
    payload = json.loads(_OVERRIDES.read_text(encoding="utf-8"))
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    repair = decisions["v52-tui-checkpoint-readiness-repair-v1"]
    assert repair["status"] == "accepted"
    assert repair["route"] == "report_only_tui_checkpoint_recovery|ALL"
    assert repair["decision_source"].endswith(
        "v52-tui-checkpoint-readiness-repair-v1.json"
    )
    _assert_approved_freshness_proposal(payload)
