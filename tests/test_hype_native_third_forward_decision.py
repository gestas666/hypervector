"""Pre-registered decision rule for the third HYPE-native forward path."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.cohort_change_proposals import normalize_change_proposals
from hypervector.research.hype_native_third_forward_decision import (
    decide_hype_native_third_forward,
)


def test_supportive_exact_result_requests_human_approval() -> None:
    """A robust third result creates a proposal but cannot deploy it."""
    report = decide_hype_native_third_forward(_resolution(13.0), _journal())

    assert report["decision"] == "request_human_approval_for_hype_native_long_v3"
    assert report["metrics"]["combined_net_excluding_largest_winner_usd"] > 0.0
    assert report["contract"]["automatic_live_change"] is False
    proposals = normalize_change_proposals(report["change_proposals"])
    assert proposals[0]["approval_status"] == "pending_human_approval"
    assert proposals[0]["explicit_approval_requested"] is True
    assert proposals[0]["validation_completed"] == [
        "Exact mark path, official funding, and frozen lifecycle economics."
    ]


def test_threshold_equality_is_not_supportive() -> None:
    """The frozen rule says greater than, so equality cannot be promoted."""
    report = decide_hype_native_third_forward(_resolution(12.093905), _journal())

    assert report["decision"] == "reject_hype_native_live_replacement"
    assert report["metrics"]["combined_net_excluding_largest_winner_usd"] == 0.0
    assert report["change_proposals"] == []


def test_changed_preregistered_threshold_is_rejected() -> None:
    """Post-outcome threshold movement must fail rather than change the decision."""
    journal = deepcopy(_journal())
    journal["preregistered_decision_rule"]["third_path_after_funding_threshold_usd"] = (
        1.0
    )

    with pytest.raises(ValueError, match="threshold does not reconcile"):
        decide_hype_native_third_forward(_resolution(13.0), journal)


def test_unverified_resolution_contract_is_rejected() -> None:
    """Execution-capable or malformed evidence cannot drive the proposal."""
    resolution = deepcopy(_resolution(13.0))
    resolution["contract"]["execution_authority"] = "live"

    with pytest.raises(ValueError, match="resolution contract"):
        decide_hype_native_third_forward(resolution, _journal())


def test_technical_rejection_terminates_without_economic_claim() -> None:
    """An unconfirmed proxy stop rejects promotion without inventing PnL."""
    report = decide_hype_native_third_forward(_technical_resolution(), _journal())

    assert report["decision"] == "reject_hype_native_live_replacement"
    assert report["metrics"]["third_net_pnl_usd_after_funding"] is None
    assert report["technical_evidence"]["resolution_status"] == (
        "technical_evidence_rejected"
    )
    assert report["technical_evidence"]["technical_rejection_reason"] == (
        "bbo_proxy_exit_not_confirmed_by_mark"
    )
    assert report["change_proposals"] == []


def _resolution(net: float) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_exact_post_close_resolution_report_only",
        "contract": {"report_only": True, "execution_authority": "none"},
        "identity": {
            "profile_id": "multi_asset_growth_first_5000_hype_native_long_challenger_v54",
            "profile_fingerprint": "1c0beafb19ef1b8c5594d3bf1aa6a23eeff12f28f540d958953cc25e8bff1643",
            "strategy_id": "hype_native_breakout_onset_long_v3",
            "symbol": "HYPE",
        },
        "lifecycles": [
            {
                "side": "long",
                "exit_reason": "maximum_hold",
                "funding_event_count": 8,
                "net_pnl_usd_after_funding": net,
                "mark_stop_truth": "confirmed_no_earlier_mark_stop",
            }
        ],
        "summary": {"trades": 1, "net_pnl_usd_after_funding": net},
    }


def _technical_resolution() -> dict[str, object]:
    report = _resolution(0.0)
    report["resolution_status"] = "technical_evidence_rejected"
    report["lifecycles"][0].update(
        {
            "net_pnl_usd_after_funding": None,
            "exit_reason": "protective_stop_bbo_proxy",
            "mark_stop_truth": "confirmed_no_earlier_mark_stop",
            "technical_evidence_status": "rejected",
            "technical_rejection_reason": "bbo_proxy_exit_not_confirmed_by_mark",
        }
    )
    report["summary"] = {
        "resolved_trades": 0,
        "technically_rejected_lifecycles": 1,
    }
    return report


def _journal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "hypothesis_id": "v54-hype-native-third-forward-preregistered-decision-v1",
        "automatic_live_change": False,
        "explicit_approval_requested": False,
        "preregistered_decision_rule": {
            "prior_two_path_net_usd_after_funding": 1.660554,
            "prior_largest_winner_usd": 13.754459,
            "prior_loss_usd": -12.093905,
            "third_path_after_funding_threshold_usd": 12.093905,
        },
    }
