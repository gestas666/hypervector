"""Pre-registered decision for the third HYPE-native forward lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.research.cohort_change_proposals import normalize_change_proposals

Record = Mapping[str, object]
_RESOLUTION_MODE = "hype_native_v54_exact_post_close_resolution_report_only"
_HYPOTHESIS = "v54-hype-native-third-forward-preregistered-decision-v1"
_PROFILE = "multi_asset_growth_first_5000_hype_native_long_challenger_v54"
_FINGERPRINT = "1c0beafb19ef1b8c5594d3bf1aa6a23eeff12f28f540d958953cc25e8bff1643"
_STRATEGY = "hype_native_breakout_onset_long_v3"


def decide_hype_native_third_forward(
    resolution: Record, journal: Record
) -> dict[str, object]:
    """Evaluate the frozen decision rule without live execution authority."""
    lifecycle, third = _require_resolution(resolution)
    prior = _require_journal(journal)
    if third is None:
        return _technical_rejection_decision(lifecycle, prior)
    values = [prior["loss"], prior["winner"], third]
    combined = sum(values)
    largest = max(value for value in values if value > 0.0)
    excluding_largest = combined - largest
    supportive = third > prior["threshold"] and excluding_largest > 0.0
    proposals = [_proposal()] if supportive else []
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_third_forward_decision_report_only",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
        },
        "decision": (
            "request_human_approval_for_hype_native_long_v3"
            if supportive
            else "reject_hype_native_live_replacement"
        ),
        "metrics": {
            "third_net_pnl_usd_after_funding": third,
            "threshold_usd": prior["threshold"],
            "combined_net_pnl_usd_after_funding": combined,
            "combined_largest_winner_usd": largest,
            "combined_net_excluding_largest_winner_usd": excluding_largest,
        },
        "technical_evidence": {
            "mark_stop_truth": lifecycle["mark_stop_truth"],
            "funding_event_count": lifecycle["funding_event_count"],
        },
        "change_proposals": normalize_change_proposals(proposals),
    }


def _require_resolution(resolution: Record) -> tuple[Record, float | None]:
    contract = _mapping(resolution.get("contract"), "resolution contract")
    if (
        resolution.get("schema_version") != 1
        or resolution.get("mode") != _RESOLUTION_MODE
        or contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("HYPE third-forward resolution contract is invalid")
    _require_identity(_mapping(resolution.get("identity"), "resolution identity"))
    rows = resolution.get("lifecycles")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise ValueError("HYPE third-forward resolution must contain one lifecycle")
    lifecycle = rows[0]
    if resolution.get("resolution_status") == "technical_evidence_rejected":
        _require_technical_rejection(resolution, lifecycle)
        return lifecycle, None
    _require_lifecycle(lifecycle)
    net = _number(lifecycle.get("net_pnl_usd_after_funding"), "third PnL")
    summary = _mapping(resolution.get("summary"), "resolution summary")
    summary_net = _number(summary.get("net_pnl_usd_after_funding"), "summary PnL")
    if summary.get("trades") != 1 or not math.isclose(net, summary_net, abs_tol=1e-9):
        raise ValueError("HYPE third-forward resolution summary does not reconcile")
    return lifecycle, net


def _require_technical_rejection(resolution: Record, lifecycle: Record) -> None:
    summary = _mapping(resolution.get("summary"), "rejection summary")
    valid = (
        lifecycle.get("side") == "long"
        and lifecycle.get("exit_reason") == "protective_stop_bbo_proxy"
        and lifecycle.get("mark_stop_truth") == "confirmed_no_earlier_mark_stop"
        and lifecycle.get("technical_evidence_status") == "rejected"
        and lifecycle.get("technical_rejection_reason")
        == "bbo_proxy_exit_not_confirmed_by_mark"
        and lifecycle.get("net_pnl_usd_after_funding") is None
        and summary.get("resolved_trades") == 0
        and summary.get("technically_rejected_lifecycles") == 1
    )
    if not valid:
        raise ValueError("HYPE third-forward technical rejection is invalid")


def _technical_rejection_decision(
    lifecycle: Record, prior: Mapping[str, float]
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_third_forward_decision_report_only",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
        },
        "decision": "reject_hype_native_live_replacement",
        "metrics": {
            "third_net_pnl_usd_after_funding": None,
            "threshold_usd": prior["threshold"],
            "combined_net_pnl_usd_after_funding": None,
            "combined_largest_winner_usd": None,
            "combined_net_excluding_largest_winner_usd": None,
        },
        "technical_evidence": {
            "resolution_status": "technical_evidence_rejected",
            "mark_stop_truth": lifecycle.get("mark_stop_truth"),
            "technical_rejection_reason": lifecycle.get("technical_rejection_reason"),
        },
        "change_proposals": [],
    }


def _require_identity(identity: Record) -> None:
    expected = {
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "strategy_id": _STRATEGY,
        "symbol": "HYPE",
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("HYPE third-forward resolution identity is invalid")


def _require_lifecycle(lifecycle: Record) -> None:
    if lifecycle.get("side") != "long":
        raise ValueError("HYPE third-forward lifecycle must be long")
    if lifecycle.get("mark_stop_truth") not in {
        "confirmed_mark_stop",
        "confirmed_no_earlier_mark_stop",
    }:
        raise ValueError("HYPE third-forward mark evidence is unresolved")
    count = lifecycle.get("funding_event_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("HYPE third-forward funding count is invalid")
    if not isinstance(lifecycle.get("exit_reason"), str):
        raise ValueError("HYPE third-forward exit reason is invalid")


def _require_journal(journal: Record) -> dict[str, float]:
    if (
        journal.get("schema_version") != 1
        or journal.get("hypothesis_id") != _HYPOTHESIS
        or journal.get("automatic_live_change") is not False
        or journal.get("explicit_approval_requested") is not False
    ):
        raise ValueError("HYPE preregistered decision contract is invalid")
    rule = _mapping(journal.get("preregistered_decision_rule"), "decision rule")
    prior = _number(rule.get("prior_two_path_net_usd_after_funding"), "prior net")
    winner = _number(rule.get("prior_largest_winner_usd"), "prior winner")
    loss = _number(rule.get("prior_loss_usd"), "prior loss")
    threshold = _number(
        rule.get("third_path_after_funding_threshold_usd"), "third threshold"
    )
    if winner <= 0.0 or loss >= 0.0 or not math.isclose(prior, winner + loss):
        raise ValueError("HYPE preregistered prior outcomes do not reconcile")
    if not math.isclose(threshold, abs(loss), abs_tol=1e-9):
        raise ValueError("HYPE preregistered threshold does not reconcile")
    return {"winner": winner, "loss": loss, "threshold": threshold}


def _proposal() -> dict[str, object]:
    return {
        "proposal_id": "v54-hype-native-long-replacement-v1",
        "approval_status": "pending_human_approval",
        "execution_effect": "proposal_only",
        "automatic_live_change": False,
        "recommendation": "Replace live HYPE compression with HYPE-native long v3.",
        "why_now": "The frozen third-path robustness rule passed after exact costs.",
        "evidence_reviewed": ["Three compatible HYPE-native forward lifecycles."],
        "observed_problem_or_opportunity": "Compression missed native momentum.",
        "applicable_market_regime": "Fresh five-minute HYPE breakout onset.",
        "alternatives_considered": ["Keep compression.", "Restore both sides."],
        "proposed_live_change": "HYPE-only long entries; short onset exits only.",
        "expected_upside": "Recover HYPE-native momentum opportunities.",
        "main_risks_and_failure_modes": ["N=3 remains a small forward sample."],
        "validation_completed": [
            "Exact mark path, official funding, and frozen lifecycle economics."
        ],
        "validation_still_required": ["Flat preflight and successor acceptance."],
        "success_metrics": ["Positive compatible net excluding largest winner."],
        "failure_or_rollback_triggers": ["Wrong-side action or negative window."],
        "confidence_level": "low",
        "explicit_approval_requested": True,
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"HYPE {label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HYPE {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"HYPE {label} must be finite")
    return result
