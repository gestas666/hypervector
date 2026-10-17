"""Exact identity contract for the v56 continuous-improvement feed."""

from __future__ import annotations

import pytest

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_ROOT = Path(__file__).parents[1]
_CONFIG = (
    _ROOT / "configs/multi_asset_growth_first_5000_btc_tuned_v2_increment_v56.toml"
)
_OVERRIDES = _ROOT / "configs/research/cohort_improvement_decision_overrides_v56.json"
_SCRIPT = _ROOT / "scripts/cohort_improvement_monitor.py"
_TUNED_ROUTE = "hulk_expansion_short_tuned_v2|BTC"
_SPCX_HYPOTHESIS = "v56-spcx-cash-open-forward-20260818-v1"
_SPCX_PREREGISTRATION = (
    "../../docs/research-journal/"
    "v56-spcx-cash-open-forward-preregistration-20260818-v1.json"
)
_SPCX_DECISION = (
    "../../docs/research-journal/v56-spcx-cash-open-forward-decision-20260818-v1.json"
)
_SPCX_RESOLUTION = (
    "../../docs/research-journal/"
    "v56-spcx-cash-open-first-long-resolution-20260818-v1.json"
)
_SPCX_EXIT_PREREGISTRATION = (
    "../../docs/research-journal/"
    "v56-spcx-long-exit-giveback-challenger-preregistration-20260818-v1.json"
)
_SPCX_EXIT_RESULT = (
    "../../data/logs/research/"
    "xyz_spcx_cash_open_long_exit_challenger_development_20260818_v1.json"
)
_SPCX_LIVE_AUDIT = (
    "../../data/logs/research/bidirectional_cohort/"
    "v56_spcx_cash_open_resolved_20260818T1420Z.json"
)
_SPCX_ENTRY_DIAGNOSIS = "v56-spcx-long-entry-quality-v1"
_SPCX_ENTRY_PREREGISTRATION = (
    "../../docs/research-journal/"
    "v56-spcx-long-entry-quality-preregistration-20260818-v1.json"
)
_SPCX_ENTRY_RESULT = (
    "../../data/logs/research/"
    "xyz_spcx_cash_open_long_entry_diagnosis_development_20260818_v1.json"
)
_SPCX_CONTAINMENT = (
    "../../docs/research-journal/"
    "v56-spcx-long-side-containment-proposal-20260818-v1.json"
)
_SPCX_SHORT_FORWARD = "v56-spcx-short-live-lifecycle-v1"
_ROUTES = {
    "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
    "hulk_expansion_short_robust_v3|BTC",
    _TUNED_ROUTE,
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
}


def test_v56_override_is_exact_report_only_and_has_all_routes() -> None:
    """The feed must bind v56 without granting further live authority."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    payload = json.loads(_OVERRIDES.read_text())

    assert payload["source_profile_id"] == config.profile_id
    assert payload["source_profile_fingerprint"] == config.profile_fingerprint
    assert set(payload["routes"]) == _ROUTES
    assert len(payload["change_proposals"]) == 1
    assert payload["change_proposals"][0]["proposal_id"] == (
        "v56-disable-spcx-long-retain-short-v1"
    )
    assert payload["change_proposals"][0]["approval_status"] == (
        "pending_human_approval"
    )
    assert payload.get("standing_live_change_approval") is None
    assert payload["contract"]["execution_authority"] == "none"
    assert payload["contract"]["automatic_promotion"] is False


@pytest.mark.evidence
def test_v56_override_evidence_reconciles_and_tracks_first_v2_lifecycle() -> None:
    """The monitor must load exact bytes and retain the live v2 experiment."""
    spec = spec_from_file_location("v56_improvement_monitor", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load cohort improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    payload, raw = module._load_decision_overrides(_OVERRIDES)
    active = {row["hypothesis_id"]: row for row in payload["active_hypotheses"]}

    assert raw == _OVERRIDES.read_bytes()
    evidence = {row["path"]: row for row in payload["evidence"]}

    assert len(evidence) == 16
    assert evidence[_SPCX_PREREGISTRATION]["sha256"] == (
        "11a3013341191b6cacaeed21f28b84f45f2b38a8e70aa45abb8071097d8a85d1"
    )
    assert evidence[_SPCX_DECISION]["sha256"] == (
        "cfd3c067e9795b5c993cc098958e25dcbc2aca7cbe84fa2b25e648eabbae6f11"
    )
    assert evidence[_SPCX_RESOLUTION]["sha256"] == (
        "026fc938233943f6364131122a97a6b192c1dfc2ffecce23cafde7c7c6ac5108"
    )
    assert evidence[_SPCX_EXIT_PREREGISTRATION]["sha256"] == (
        "0d07332ff1cc9ca51e0dcdf54416f8d0b1fa20c274b27f76a7dfbe21ce546f16"
    )
    assert evidence[_SPCX_EXIT_RESULT]["sha256"] == (
        "d307c5ea128dbfafc23533e35db228fe77014fd955e88c3ae38a6c70bfe1d844"
    )
    assert evidence[_SPCX_LIVE_AUDIT]["sha256"] == (
        "b5b151c78f246c322d9f561495bb423ab1fd90eaee827df37093aec467df01d5"
    )
    assert evidence[_SPCX_ENTRY_PREREGISTRATION]["sha256"] == (
        "5332ce8a2af55d9af34951d5c256cd3f81472fc96a51e0cdc9f07a997df14630"
    )
    assert evidence[_SPCX_ENTRY_RESULT]["sha256"] == (
        "0b5eb1b410b6a654ca9146d61f1ec7b57031da02fd878d2fa4c77595a258033d"
    )
    assert evidence[_SPCX_CONTAINMENT]["sha256"] == (
        "7fb97db8fe78498c297037e58d4494fe59d579ce794d940a25c0205053dadb80"
    )
    assert active["v56-first-tuned-v2-live-lifecycle-v1"]["route"] == _TUNED_ROUTE
    assert active["v56-first-tuned-v2-live-lifecycle-v1"]["status"] == "being_tested"
    assert active["v56-first-tuned-v2-live-lifecycle-v1"]["execution_effect"] == (
        "report_only"
    )
    assert _SPCX_HYPOTHESIS not in active
    assert _SPCX_ENTRY_DIAGNOSIS not in active
    assert active[_SPCX_SHORT_FORWARD]["status"] == "being_tested"
    assert active[_SPCX_SHORT_FORWARD]["decision_source"] == _SPCX_CONTAINMENT
    assert active[_SPCX_SHORT_FORWARD]["execution_effect"] == "report_only"


def test_v56_override_closes_diagnosis_and_requests_long_containment() -> None:
    """Close the diagnosis and request, but do not execute, side containment."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}
    route = payload["routes"][
        "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX"
    ]

    assert decisions[_SPCX_HYPOTHESIS]["status"] == "accepted"
    assert decisions[_SPCX_HYPOTHESIS]["proposed_live_change"] is None
    assert decisions["v56-spcx-long-fixed-target-family-v1"]["status"] == "rejected"
    assert (
        decisions["v56-spcx-long-fixed-target-family-v1"]["proposed_live_change"]
        is None
    )
    assert decisions[_SPCX_ENTRY_DIAGNOSIS]["status"] == "accepted"
    assert decisions[_SPCX_ENTRY_DIAGNOSIS]["decision_source"] == _SPCX_ENTRY_RESULT
    assert route["next_experiment"] == "collect_side_specific_evidence"
    assert route["decision_source"] == _SPCX_CONTAINMENT
    proposal = payload["change_proposals"][0]
    assert proposal["explicit_approval_requested"] is True
    assert proposal["execution_effect"] == "proposal_only"
    assert proposal["automatic_live_change"] is False
