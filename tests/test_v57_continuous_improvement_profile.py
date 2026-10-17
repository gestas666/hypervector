"""Exact identity contract for the v57 continuous-improvement feed."""

from __future__ import annotations

import pytest

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from typing import cast

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_ROOT = Path(__file__).parents[1]
_CONFIG = (
    _ROOT / "configs/multi_asset_growth_first_5000_spcx_short_containment_v57.toml"
)
_OVERRIDES = _ROOT / "configs/research/cohort_improvement_decision_overrides_v57.json"
_CADENCE = (
    _ROOT / "docs/research-journal/v57-route-cadence-review-thresholds-20260818-v2.json"
)
_SCRIPT = _ROOT / "scripts/cohort_improvement_monitor.py"
_SPCX_ROUTE = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX"
_HYPE_ROUTE = "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
_ROUTES = {
    _SPCX_ROUTE,
    "hulk_expansion_short_robust_v3|BTC",
    "hulk_expansion_short_tuned_v2|BTC",
    _HYPE_ROUTE,
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
}
JsonRecord = dict[str, object]


def _tracker_source_names(payload: JsonRecord) -> set[str]:
    evidence = cast(list[JsonRecord], payload["evidence"])
    return {cast(str, row["path"]).rsplit("/", maxsplit=1)[-1] for row in evidence}


def _assert_tracker_evidence(payload: JsonRecord) -> None:
    evidence = cast(list[JsonRecord], payload["evidence"])
    required = {
        "v57-continuous-improvement-baseline-20260818-v5.json",
        "v57-hype-alignment-both-side-live-lifecycle-preregistration-20260819-v5.json",
        "v57_hype_first_true_onset_stop_path_20260818_v2.json",
        "v57_hype_first_true_onset_process_parity_20260818_v1.json",
        "v57-btc-tuned-v2-short-live-lifecycle-preregistration-20260819-v2.json",
        "v57-spcx-short-live-lifecycle-preregistration-20260819-v2.json",
        "v57-btc-robust-v3-short-live-lifecycle-preregistration-20260819-v2.json",
        "v57-btc-liquidity-sweep-long-live-lifecycle-preregistration-20260819-v2.json",
        "v57-mu-source-native-lifecycle-result-20260818-v1.json",
        "v57-hype-native-lineage-segmentation-20260818-v1.json",
    }
    historical = (
        "v57-hype-alignment-both-side-live-lifecycle-tracker-20260818-v1.json",
        "v57-hype-alignment-both-side-live-lifecycle-preregistration-20260818-v2.json",
        "v57-hype-alignment-both-side-live-lifecycle-preregistration-20260818-v3.json",
    )
    assert len(evidence) == 38
    assert all(
        any(cast(str, row["path"]).endswith(name) for row in evidence)
        for name in historical
    )
    assert required <= _tracker_source_names(payload)


def _indexed_rows(payload: JsonRecord, key: str) -> dict[str, JsonRecord]:
    rows = cast(list[JsonRecord], payload[key])
    return {cast(str, row["hypothesis_id"]): row for row in rows}


def _assert_active_hypotheses(active: dict[str, JsonRecord]) -> None:
    spcx = active["v57-spcx-short-live-lifecycle-v1"]
    assert spcx["route"] == _SPCX_ROUTE
    assert spcx["status"] == "being_tested"
    assert cast(str, spcx["decision_source"]).endswith(
        "v57-spcx-short-live-lifecycle-preregistration-20260819-v2.json"
    )
    assert all(row["execution_effect"] == "report_only" for row in active.values())
    tuned = active["v57-first-tuned-v2-live-lifecycle-v1"]
    assert cast(str, tuned["decision_source"]).endswith(
        "v57-btc-tuned-v2-short-live-lifecycle-preregistration-20260819-v2.json"
    )
    hype = active["v57-hype-alignment-both-side-live-lifecycle-v1"]
    assert hype["route"] == _HYPE_ROUTE
    assert hype["status"] == "being_tested"
    assert cast(str, hype["decision_source"]).endswith(
        "v57-hype-alignment-both-side-live-lifecycle-preregistration-20260819-v5.json"
    )
    assert "long and short" in cast(str, hype["minimum_evidence"])
    assert hype["automatic_live_change"] is False
    robust = active["v57-first-robust-v3-live-lifecycle-v1"]
    assert robust["route"] == "hulk_expansion_short_robust_v3|BTC"
    assert cast(str, robust["decision_source"]).endswith(
        "v57-btc-robust-v3-short-live-lifecycle-preregistration-20260819-v2.json"
    )
    sweep = active["v57-first-liquidity-sweep-long-live-lifecycle-v1"]
    assert sweep["route"] == "liquidity_sweep_long_1h_stop60_target60_v2|BTC"
    assert cast(str, sweep["decision_source"]).endswith(
        "v57-btc-liquidity-sweep-long-live-lifecycle-preregistration-20260819-v2.json"
    )


def _assert_hype_and_brent_decisions(decisions: dict[str, JsonRecord]) -> None:
    lineage = decisions["v57-hype-native-lineage-segmentation-v1"]
    assert lineage["status"] == "rejected"
    assert lineage["classification"] == "not_a_comparable_strategy_aggregate"
    assert lineage["route"] == "hype_breakout_onset_bidirectional_v1|mixed"
    assert "14 native HYPE" in cast(str, lineage["decision_reason"])
    assert "24 cross-asset" in cast(str, lineage["decision_reason"])
    assert lineage["reopen_condition"]
    native = decisions["v57-hype-native-long-replacement-forward-update-v1"]
    assert native["status"] == "rejected"
    assert native["route"] == "hype_native_breakout_onset_long_v3|HYPE"
    assert native["reopen_condition"]
    relaxation = decisions["v52-hype-noncompression-alignment-relaxation"]
    assert relaxation["status"] == "rejected"
    assert relaxation["experiment"] == "remove_compression_and_pullback_prerequisites"
    assert relaxation["reopen_condition"]
    filtered = decisions["v57-hype-first-true-onset-filter-result-v1"]
    assert filtered["status"] == "rejected"
    assert filtered["route"] == _HYPE_ROUTE
    assert "protective stop proxy" in cast(str, filtered["decision_reason"])
    assert filtered["reopen_condition"]
    brent = decisions["v57-brentoil-oil-shock-external-candidate-v1"]
    assert brent["status"] == "deferred"
    assert cast(str, brent["route"]).endswith("|xyz:BRENTOIL")
    assert cast(str, brent["decision_source"]).endswith(
        "v57-brentoil-prospective-loss-update-20260818-v1.json"
    )
    assert "prospective short stopped out" in cast(str, brent["decision_reason"])
    assert brent["reopen_condition"]
    continuation = decisions["v57-brentoil-oil-shock-continuation-development-v1"]
    assert continuation["status"] == "rejected"
    assert cast(str, continuation["route"]).endswith("|xyz:BRENTOIL")
    assert "all three chronological stress folds lost" in cast(
        str, continuation["decision_reason"]
    )
    assert continuation["reopen_condition"]


def _assert_other_rejected_decisions(decisions: dict[str, JsonRecord]) -> None:
    expected = {
        "v57-sol-failed-range-reclaim-screen-v1": "research_only_range_reclaim_v1|SOL",
        "v57-btc-sol-ema5-speed-continuation-development-v1": (
            "research_only_ema5_speed_continuation|BTC,SOL"
        ),
        "v57-mu-transport-parity-forward-v2": (
            "research_only_mu_breakout_pressure_transport_parity|xyz:MU"
        ),
        "v57-mu-source-native-lifecycle-replay-v1": (
            "research_only_mu_breakout_pressure_source_native|xyz:MU"
        ),
        "v57-eth-pullback-live-addition-v1": (
            "eth_breakout_precompression_pullback_bidirectional_v1|ETH"
        ),
        "v57-btc-sweep-primary-trigger-relaxation-v1": (
            "liquidity_sweep_long_1h_stop60_target60_v2|BTC"
        ),
        "v57-btc-hulk-v2-long-restoration-v1": (
            "hulk_expansion_bidirectional_tuned_v2|BTC"
        ),
    }
    for hypothesis_id, route in expected.items():
        row = decisions[hypothesis_id]
        assert row["status"] == "rejected"
        assert row["route"] == route
        assert row["reopen_condition"]
    assert "development, validation, and pseudo-holdout" in cast(
        str, decisions["v57-sol-failed-range-reclaim-screen-v1"]["decision_reason"]
    )
    assert "all three stress folds" in cast(
        str,
        decisions["v57-btc-sol-ema5-speed-continuation-development-v1"][
            "decision_reason"
        ],
    )
    assert "frozen generator" in cast(
        str, decisions["v57-mu-transport-parity-forward-v2"]["decision_reason"]
    )
    assert "1 win and 4 losses" in cast(
        str,
        decisions["v57-mu-source-native-lifecycle-replay-v1"]["decision_reason"],
    )
    assert "validation replay lost" in cast(
        str, decisions["v57-btc-hulk-v2-long-restoration-v1"]["decision_reason"]
    )


def test_v57_override_is_exact_report_only_and_tracks_all_routes() -> None:
    """The monitor must bind the live successor without execution authority."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    payload = json.loads(_OVERRIDES.read_text())

    assert payload["source_profile_id"] == config.profile_id
    assert payload["source_profile_fingerprint"] == config.profile_fingerprint
    assert set(payload["routes"]) == _ROUTES
    assert payload["routes"][_SPCX_ROUTE]["next_experiment"] == (
        "collect_side_specific_evidence"
    )
    assert payload["routes"][_SPCX_ROUTE]["decision_source"].endswith(
        "v57-spcx-short-live-lifecycle-preregistration-20260819-v2.json"
    )
    assert payload["routes"]["hulk_expansion_short_tuned_v2|BTC"][
        "decision_source"
    ].endswith("v57-btc-tuned-v2-short-live-lifecycle-preregistration-20260819-v2.json")
    hype = payload["routes"][
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
    ]
    assert hype["next_experiment"] == "collect_both_side_live_execution"
    assert hype["decision_source"].endswith(
        "v57-hype-alignment-both-side-live-lifecycle-preregistration-20260819-v5.json"
    )
    assert len(hype["supporting_evidence"]) == 6
    assert any(
        path.endswith("v57-hype-native-forward-update-20260818-v1.json")
        for path in hype["supporting_evidence"]
    )
    assert any(
        path.endswith("v57-continuous-improvement-baseline-20260818-v5.json")
        for path in hype["supporting_evidence"]
    )
    assert any(
        path.endswith("v57_hype_first_true_onset_process_parity_20260818_v1.json")
        for path in hype["supporting_evidence"]
    )
    assert payload["change_proposals"] == []
    assert payload["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def test_v57_freezes_route_specific_zero_signal_review_clocks() -> None:
    """Sparse routes must not share one vague portfolio inactivity deadline."""
    payload = json.loads(_OVERRIDES.read_text())
    triggers = payload["review_triggers"]["route_zero_signal"]

    assert set(triggers) == _ROUTES
    assert {route: row["threshold_seconds"] for route, row in triggers.items()} == {
        _SPCX_ROUTE: 7 * 24 * 60 * 60,
        "hulk_expansion_short_robust_v3|BTC": 25 * 24 * 60 * 60,
        "hulk_expansion_short_tuned_v2|BTC": 7 * 24 * 60 * 60,
        _HYPE_ROUTE: 14 * 24 * 60 * 60,
        "liquidity_sweep_long_1h_stop60_target60_v2|BTC": 25 * 24 * 60 * 60,
    }
    assert sorted(row["priority"] for row in triggers.values()) == [1, 2, 3, 4, 5]
    assert all(row["contract"]["report_only"] is True for row in triggers.values())
    assert all(
        row["contract"]["automatic_live_change"] is False for row in triggers.values()
    )
    assert all(
        row["decision_source"].endswith(
            "v57-route-cadence-review-thresholds-20260818-v2.json"
        )
        for row in triggers.values()
    )
    assert any(
        row["path"].endswith("v57-route-cadence-review-thresholds-20260818-v2.json")
        for row in payload["evidence"]
    )


def test_v57_spcx_cadence_evidence_uses_active_short_scope() -> None:
    """The clock sensitivity must match V57's short-only SPCX authority."""
    payload = json.loads(_CADENCE.read_text())
    spcx = payload["route_thresholds"][_SPCX_ROUTE]

    assert payload["hypothesis_id"] == "v57-route-zero-signal-cadence-review"
    assert payload["revision_number"] == 1
    assert spcx["active_execution_directions"] == ["short"]
    assert spcx["historical_trades_per_week"] == 2.164568081991215
    assert spcx["expected_events_at_threshold_sensitivity"] == 2.164568081991215
    assert spcx["stationary_poisson_zero_event_probability_sensitivity"] == 0.1148
    assert spcx["threshold_days"] == 7
    assert payload["runtime_strategy_changed"] is False


@pytest.mark.evidence
def test_v57_override_evidence_reconciles_and_retains_short_hypothesis() -> None:
    """Every research input must reconcile before the monitor can publish."""
    spec = spec_from_file_location("v57_improvement_monitor", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load cohort improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    payload, raw = module._load_decision_overrides(_OVERRIDES)
    assert raw == _OVERRIDES.read_bytes()
    _assert_tracker_evidence(payload)
    _assert_active_hypotheses(_indexed_rows(payload, "active_hypotheses"))
    _assert_hype_and_brent_decisions(_indexed_rows(payload, "hypothesis_decisions"))
    _assert_other_rejected_decisions(_indexed_rows(payload, "hypothesis_decisions"))
