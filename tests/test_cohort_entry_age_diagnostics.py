"""Tests for report-only cohort entry-age diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hypervector.research.cohort_entry_age_diagnostics import (
    build_entry_age_diagnostics,
)
from hypervector.research.cohort_live_audit_routing import build_routing_summary

_DECISION_MS = 2_000_000


def test_ineligible_late_routing_is_latent_not_executed() -> None:
    """An ineligible late cycle must not be labeled an executed breach."""
    report = build_entry_age_diagnostics(
        _cycle(cutoff_age_ms=25_000, routing_age_ms=31_000),
        _identity(),
    )

    route = report["by_provider_symbol"]["provider_v1|BTC"]
    assert route["evaluations"] == 1
    assert route["eligible_evaluations"] == 0
    assert route["minimum_initial_cutoff_headroom_ms"] == 5_000
    assert route["minimum_routing_emission_headroom_ms"] == -1_000
    assert route["latent_over_limit_ineligible_evaluations"] == 1
    assert report["enter_actions_routing_emission_over_limit"] == 0
    assert report["executed_late_entries_proven"] is False


def test_enter_action_after_limit_is_potential_breach_not_submit_proof() -> None:
    """A late emitted entry is actionable evidence without a submit timestamp."""
    report = build_entry_age_diagnostics(
        _cycle(
            cutoff_age_ms=25_000,
            routing_age_ms=31_000,
            eligible=True,
            enter_action=True,
        ),
        _identity(),
    )

    route = report["by_provider_symbol"]["provider_v1|BTC"]
    assert route["eligible_evaluations"] == 1
    assert route["enter_actions"] == 1
    assert route["eligible_routing_emission_over_limit"] == 1
    assert route["enter_actions_routing_emission_over_limit"] == 1
    assert report["enter_actions_routing_emission_over_limit"] == 1
    assert report["executed_late_entries_proven"] is False
    assert report["submission_timestamp_observed"] is False


def test_exact_submission_evidence_proves_entry_enforcement() -> None:
    """A serialized final clock must replace routing-time inference."""
    report = build_entry_age_diagnostics(
        _cycle(
            cutoff_age_ms=25_000,
            routing_age_ms=31_000,
            eligible=True,
            enter_action=True,
            submission_age_ms=29_000,
            submission_boundary="sdk_dispatch",
        ),
        _identity(),
    )

    route = report["by_provider_symbol"]["provider_v1|BTC"]
    assert report["submission_timestamp_observed"] is True
    assert report["entry_submission_enforcement_observed"] is True
    assert report["submitted_entries"] == 1
    assert route["maximum_submission_age_ms"] == 29_000
    assert route["minimum_submission_headroom_ms"] == 1_000
    assert route["status"] == "sdk_dispatch_contract_observed"


def test_stale_submission_evidence_proves_fail_closed_withholding() -> None:
    """A stale entry must remain attributable without becoming an action."""
    rows = _cycle(cutoff_age_ms=25_000, routing_age_ms=31_000, eligible=True)
    routing_payload = rows[0]["payload"]
    assert isinstance(routing_payload, dict)
    routing_payload["withheld"] = [
        {
            "strategy_id": "provider_v1",
            "symbol": "BTC",
            "decision_time_ms": _DECISION_MS,
            "reason": "stale_before_submission",
            "submission_observed_at_ms": _DECISION_MS + 31_000,
            "submission_age_ms": 31_000,
            "submission_limit_ms": 30_000,
        }
    ]

    report = build_entry_age_diagnostics(rows, _identity())

    route = report["by_provider_symbol"]["provider_v1|BTC"]
    assert report["submission_timestamp_observed"] is True
    assert report["stale_entries_withheld"] == 1
    assert route["maximum_withheld_submission_age_ms"] == 31_000
    assert route["status"] == "stale_entry_withholding_observed"


def test_exact_limit_remains_within_contract() -> None:
    """The configured contract permits equality at the entry-age boundary."""
    report = build_entry_age_diagnostics(
        _cycle(
            cutoff_age_ms=29_000,
            routing_age_ms=30_000,
            eligible=True,
            enter_action=True,
        ),
        _identity(),
    )

    route = report["by_provider_symbol"]["provider_v1|BTC"]
    assert route["minimum_routing_emission_headroom_ms"] == 0
    assert route["eligible_routing_emission_over_limit"] == 0
    assert route["enter_actions_routing_emission_over_limit"] == 0


def test_pre_activation_readiness_seed_is_excluded_with_provenance() -> None:
    """A deliberately historical readiness seed is not an entry opportunity."""
    report = build_entry_age_diagnostics(
        _cycle(
            cutoff_age_ms=390_000,
            routing_age_ms=400_000,
            readiness_seed=True,
        ),
        _identity(),
    )

    route = report["by_provider_symbol"]["provider_v1|BTC"]
    assert route["evaluations"] == 0
    assert route["excluded_pre_activation_readiness_seeds"] == 1
    assert route["latent_over_limit_ineligible_evaluations"] == 0
    assert route["maximum_routing_emission_age_ms"] is None


def test_missing_funding_boundary_fails_closed() -> None:
    """A routing row without its exact cutoff boundary is not measurable."""
    rows = _cycle(cutoff_age_ms=25_000, routing_age_ms=31_000)[:1]

    with pytest.raises(ValueError, match="missing funding boundary"):
        build_entry_age_diagnostics(rows, _identity())


def test_routing_summary_publishes_entry_age_diagnostics() -> None:
    """The live audit must expose the diagnostic consumed by the monitor."""
    summary = build_routing_summary(
        _cycle(cutoff_age_ms=25_000, routing_age_ms=31_000),
        _identity(),
    )

    diagnostic = summary["entry_age_diagnostics"]
    assert diagnostic["paired_cycles"] == 1
    assert diagnostic["contract"]["execution_authority"] == "none"


def test_routing_summary_marks_legacy_boundary_evidence_unavailable() -> None:
    """Older ledgers without funding windows must remain auditable."""
    summary = build_routing_summary(
        _cycle(cutoff_age_ms=25_000, routing_age_ms=31_000)[:1],
        _identity(),
    )

    diagnostic = summary["entry_age_diagnostics"]
    assert diagnostic["status"] == "unavailable_legacy_evidence"
    assert diagnostic["reason"] == "funding_boundaries_not_recorded"
    assert diagnostic["contract"]["execution_authority"] == "none"


def _identity() -> dict[str, object]:
    return {
        "payload": {
            "enabled_symbols": ["BTC"],
            "providers": [
                {
                    "strategy_id": "provider_v1",
                    "symbols": ["BTC"],
                    "execution_symbols": ["BTC"],
                    "maximum_entry_delay_seconds": 30,
                }
            ],
        }
    }


def _cycle(
    *,
    cutoff_age_ms: int,
    routing_age_ms: int,
    eligible: bool = False,
    enter_action: bool = False,
    readiness_seed: bool = False,
    submission_age_ms: int | None = None,
    submission_boundary: str | None = None,
) -> list[dict[str, object]]:
    evaluation = {
        "strategy_id": "provider_v1",
        "symbol": "BTC",
        "decision_time_ms": _DECISION_MS,
        "eligible": eligible,
        "backend_non_action_reason": (
            "pre_activation_readiness_seed" if readiness_seed else None
        ),
    }
    actions = (
        [_entry_action(submission_age_ms, submission_boundary)] if enter_action else []
    )
    return [
        {
            "event_type": "intent_routing",
            "sequence": 1,
            "observed_at_utc": _utc_text(_DECISION_MS + routing_age_ms),
            "payload": {
                "evaluations": [evaluation],
                "actions": actions,
                "withheld": [],
            },
        },
        {
            "event_type": "funding_reconciliation_window",
            "sequence": 2,
            "observed_at_utc": _utc_text(_DECISION_MS + routing_age_ms + 1),
            "payload": {
                "provider_cutoff_time_ms": _DECISION_MS + cutoff_age_ms,
                "action_count": len(actions),
            },
        },
    ]


def _entry_action(age_ms: int | None, boundary: str | None) -> dict[str, object]:
    action: dict[str, object] = {
        "action": "enter",
        "strategy_id": "provider_v1",
        "symbol": "BTC",
        "side": "long",
        "decision_time_ms": _DECISION_MS,
    }
    if age_ms is not None:
        action.update(
            {
                "submission_observed_at_ms": _DECISION_MS + age_ms,
                "submission_age_ms": age_ms,
                "submission_limit_ms": 30_000,
            }
        )
    if boundary is not None:
        action["submission_boundary"] = boundary
    return action


def _utc_text(timestamp_ms: int) -> str:
    instant = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=timestamp_ms)
    return instant.isoformat()
