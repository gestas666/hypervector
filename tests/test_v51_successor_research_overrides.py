"""Successor research priorities derived from exact v51 lifecycle evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
OVERRIDES = ROOT / "configs/research/cohort_improvement_decision_overrides_v51.json"
DISPOSITION = "docs/research-journal/v51-successor-route-disposition-v1.json"
SOL_CONTINUATION = "docs/research-journal/sol-breakout-continuation-v2.json"
OI_DELEVERAGING = "docs/research-journal/oi-forced-deleveraging-exhaustion-v2.json"
BRENTOIL_DISPOSITION = (
    "docs/research-journal/v51-brentoil-range-onset-transfer-disposition-v1.json"
)
INDEX_PRESSURE_TRANSLATION = (
    "docs/research-journal/v51-index-pressure-translation-challenger-v1.json"
)


def _payload() -> dict[str, object]:
    return json.loads(OVERRIDES.read_text())


def test_range_onset_successor_research_is_closed() -> None:
    """Resolved v51 evidence must stop further Range Onset optimization."""
    payload = _payload()
    routes = payload["routes"]
    for symbol in ("ETH", "SOL"):
        route = routes[f"range_onset_bidirectional_v1|{symbol}"]
        assert route["triage"] == "STOP"
        assert route["next_experiment"] == "new_mechanic_version_required"
        assert route["decision_source"] == DISPOSITION


def test_btc_candidates_remain_and_failed_hype_v1_is_retired() -> None:
    """The monitor retains BTC research without reopening failed HYPE v1."""
    payload = _payload()
    routes = payload["routes"]
    expected = {
        "hulk_expansion_short_robust_v3|BTC": "collect_side_specific_evidence",
        "liquidity_sweep_long_1h_stop60_target60_v2|BTC": (
            "collect_side_specific_evidence"
        ),
    }
    for route_id, experiment in expected.items():
        route = routes[route_id]
        assert route["triage"] == "REVISE"
        assert route["next_experiment"] == experiment
        assert route["decision_source"] == DISPOSITION
    hype = routes["hype_breakout_compression_pullback_bidirectional_v1|HYPE"]
    assert hype["triage"] == "STOP"
    assert hype["next_experiment"] == "new_mechanic_version_required"
    assert hype["decision_source"].endswith(
        "v51-hype-compression-alignment-causal-replay-v1.json"
    )


def test_index_routes_retain_source_native_both_side_collection() -> None:
    """The successor review must not relabel archive index evidence as live."""
    payload = _payload()
    routes = payload["routes"]
    for symbol in ("xyz:SP500", "xyz:SPCX"):
        route_id = (
            f"hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|{symbol}"
        )
        route = routes[route_id]
        assert route["triage"] == "REVISE"
        assert route["next_experiment"] == "collect_both_side_live_execution"
        assert route["historical_assessment"] == (
            "archive_mechanism_rejected_live_v3_source_transport_materially_"
            "different_forward_edge_unproven"
        )
        assert route["decision_source"].endswith(
            "v51-index-source-parity-forward-v1.json"
        )
        evidence = route["supporting_evidence"]
        assert "docs/research-journal/v51-index-mark-response-lag-v1.json" in evidence
        assert any(symbol.removeprefix("xyz:").lower() in row for row in evidence)


def test_range_onset_successor_hypothesis_is_rejected() -> None:
    """The durable hypothesis ledger must not silently reopen Range Onset."""
    payload = _payload()
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    decision = decisions["v51-range-onset-successor-retention-v1"]
    assert decision["status"] == "rejected"
    assert decision["decision_source"] == DISPOSITION
    assert decision["reopen_condition"]


def test_successor_disposition_is_hash_bound() -> None:
    """The active override manifest must bind the route disposition bytes."""
    payload = _payload()
    evidence = {row["path"]: row for row in payload["evidence"]}
    row = evidence[f"../../{DISPOSITION}"]
    path = OVERRIDES.parent / row["path"]
    assert path.is_file()
    assert row["bytes"] == path.stat().st_size


def test_rejected_sol_continuation_is_retained_and_hash_bound() -> None:
    """The monitor must not reopen the failed prospective SOL continuation."""
    payload = _payload()
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    decision = decisions["sol-breakout-continuation-after-onset"]
    assert decision["status"] == "rejected"
    assert decision["decision_source"] == SOL_CONTINUATION
    evidence = {row["path"]: row for row in payload["evidence"]}
    row = evidence[f"../../{SOL_CONTINUATION}"]
    path = OVERRIDES.parent / row["path"]
    assert row["bytes"] == path.stat().st_size


def test_rejected_oi_deleveraging_is_retained_and_hash_bound() -> None:
    """The monitor must not tune the failed OI-conditioned event family."""
    payload = _payload()
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    decision = decisions["oi-forced-deleveraging-exhaustion"]
    assert decision["status"] == "rejected"
    assert decision["decision_source"] == OI_DELEVERAGING
    evidence = {row["path"]: row for row in payload["evidence"]}
    row = evidence[f"../../{OI_DELEVERAGING}"]
    path = OVERRIDES.parent / row["path"]
    assert row["bytes"] == path.stat().st_size


def test_brentoil_range_onset_transfer_is_rejected_and_hash_bound() -> None:
    """The monitor must not transfer retired Range Onset to BRENTOIL."""
    payload = _payload()
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    decision = decisions["v51-brentoil-range-onset-transfer-v1"]
    assert decision["status"] == "rejected"
    assert decision["decision_source"] == BRENTOIL_DISPOSITION
    assert decision["reopen_condition"]
    evidence = {row["path"]: row for row in payload["evidence"]}
    row = evidence[f"../../{BRENTOIL_DISPOSITION}"]
    path = OVERRIDES.parent / row["path"]
    assert row["bytes"] == path.stat().st_size


def test_index_pressure_translation_challenger_is_forward_only() -> None:
    """Observed pressure flips may open research, never a live gate."""
    payload = _payload()
    active = {row["hypothesis_id"]: row for row in payload["active_hypotheses"]}
    hypothesis = active["v51-index-pressure-translation-persistence-v1"]
    assert hypothesis["status"] == "being_tested"
    assert hypothesis["execution_effect"] == "report_only"
    assert hypothesis["evidence_source"] == INDEX_PRESSURE_TRANSLATION
    assert hypothesis["minimum_additional_evidence"]
    evidence = {row["path"]: row for row in payload["evidence"]}
    row = evidence[f"../../{INDEX_PRESSURE_TRANSLATION}"]
    path = OVERRIDES.parent / row["path"]
    assert row["bytes"] == path.stat().st_size
