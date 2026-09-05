"""Contracts for prospective experiment evidence in the improvement digest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

import hypervector.research.cohort_continuous_improvement as continuous
from hypervector.research.cohort_prospective_experiment_evidence import (
    ObserverIdentity,
    attach_prospective_experiment_evidence,
    load_sol_route_native_observer,
)

_ROUTE = "range_onset_bidirectional_v1|SOL"


def test_pending_sol_observer_is_visible_without_becoming_a_forward_path(
    tmp_path: Path,
) -> None:
    """Pending route-native evidence must remain distinct from resolved paths."""
    observed_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    path = _write_observer(tmp_path, observed_at)

    evidence = load_sol_route_native_observer(
        path,
        _identity(),
        observed_at=observed_at + timedelta(seconds=90),
        maximum_age_seconds=360.0,
    )
    attached = attach_prospective_experiment_evidence(_digest(), evidence)
    row = attached["experiment_queue"][0]

    assert row["independent_forward_paths"] == 0
    assert row["prospective_observation"] == {
        "route": _ROUTE,
        "experiment": "collect_route_native_one_blocker_shadow",
        "availability_status": "available",
        "observer_status": "candidate_lifecycle_pending",
        "observed_at_utc": observed_at.isoformat(),
        "capture_start_utc": "2026-08-15T10:00:00+00:00",
        "raw_exact_evaluations": 65,
        "independent_onsets": 2,
        "attempts": 1,
        "deployable_attempts": 1,
        "resolved_lifecycles": 0,
        "active_pending_lifecycles": 1,
        "technically_unresolved_attempts": 0,
        "raw_resolved_lifecycles": 0,
        "raw_active_pending_lifecycles": 1,
        "portfolio_excluded_attempts": 0,
        "existing_symbol_position_attempts": 0,
        "portfolio_capacity_attempts": 0,
        "same_cycle_symbol_action_attempts": 0,
        "portfolio_state_unavailable_attempts": 0,
        "observed_sides": ["short"],
        "economic_verdict": "unavailable_until_resolved_lifecycle",
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }
    assert attached["prospective_experiment_evidence"] == [
        row["prospective_observation"]
    ]
    assert evidence.source is not None
    assert evidence.source["sha256"]


def test_stale_observer_is_explicitly_unavailable(tmp_path: Path) -> None:
    """A stale snapshot may not contribute current progress counters."""
    observed_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    path = _write_observer(tmp_path, observed_at)

    evidence = load_sol_route_native_observer(
        path,
        _identity(),
        observed_at=observed_at + timedelta(seconds=361),
        maximum_age_seconds=360.0,
    )

    assert evidence.summary == {
        "route": _ROUTE,
        "experiment": "collect_route_native_one_blocker_shadow",
        "availability_status": "unavailable_stale",
        "observer_status": "candidate_lifecycle_pending",
        "observed_at_utc": observed_at.isoformat(),
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }


def test_missing_observer_is_explicitly_unavailable(tmp_path: Path) -> None:
    """A missing observer must not suppress the rest of the digest."""
    evidence = load_sol_route_native_observer(
        tmp_path / "missing.json",
        _identity(),
        observed_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        maximum_age_seconds=360.0,
    )

    assert evidence.summary["availability_status"] == "unavailable_missing"
    assert evidence.source is None


def test_previous_run_observer_is_explicitly_unavailable(tmp_path: Path) -> None:
    """A normal backend restart must not suppress the current-run digest."""
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    payload = _observer_payload(now)
    payload["contract"]["source_run_id"] = "previous-v51-run"
    path = tmp_path / "observer.json"
    path.write_text(json.dumps(payload))

    evidence = load_sol_route_native_observer(
        path,
        _identity(),
        observed_at=now,
        maximum_age_seconds=360.0,
    )

    assert evidence.summary == {
        "route": _ROUTE,
        "experiment": "collect_route_native_one_blocker_shadow",
        "availability_status": "unavailable_previous_run",
        "observer_status": "candidate_lifecycle_pending",
        "observed_at_utc": now.isoformat(),
        "source_run_id": "previous-v51-run",
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }
    assert evidence.source is not None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("source_profile_id", "other-profile", "profile identity mismatch"),
        ("source_profile_fingerprint", "b" * 64, "fingerprint mismatch"),
    ),
)
def test_observer_identity_mismatch_is_rejected(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    """Foreign observer evidence cannot enter the active profile digest."""
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    payload = _observer_payload(now)
    payload["contract"][field] = value
    path = tmp_path / "observer.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match=message):
        load_sol_route_native_observer(
            path,
            _identity(),
            observed_at=now,
            maximum_age_seconds=360.0,
        )


def test_observer_with_execution_authority_is_rejected(tmp_path: Path) -> None:
    """Execution-capable evidence cannot be attached to research telemetry."""
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    payload = _observer_payload(now)
    payload["contract"]["execution_authority"] = "hyperliquid_mainnet"
    path = tmp_path / "observer.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="contract is invalid"):
        load_sol_route_native_observer(
            path,
            _identity(),
            observed_at=now,
            maximum_age_seconds=360.0,
        )


def test_observer_counts_must_reconcile_with_lifecycle_rows(tmp_path: Path) -> None:
    """Success-shaped coverage counters cannot exceed actual lifecycle rows."""
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    payload = _observer_payload(now)
    payload["coverage"]["resolved_executions"] = 1
    path = tmp_path / "observer.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="resolved lifecycle count"):
        load_sol_route_native_observer(
            path,
            _identity(),
            observed_at=now,
            maximum_age_seconds=360.0,
        )


def test_occupied_pending_attempt_does_not_advance_deployable_maturity(
    tmp_path: Path,
) -> None:
    """A canonical open SOL lifecycle is evidence, not incremental capacity."""
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    payload = _observer_payload(now)
    payload["portfolio_journal"] = _portfolio_journal("existing_symbol_position")
    path = tmp_path / "observer.json"
    path.write_text(json.dumps(payload))

    evidence = load_sol_route_native_observer(
        path,
        _identity(),
        observed_at=now,
        maximum_age_seconds=360.0,
    )

    summary = evidence.summary
    assert summary["attempts"] == 1
    assert summary["deployable_attempts"] == 0
    assert summary["active_pending_lifecycles"] == 0
    assert summary["portfolio_excluded_attempts"] == 1
    assert summary["existing_symbol_position_attempts"] == 1
    assert summary["observed_sides"] == []


def test_active_hypothesis_retains_prospective_maturity() -> None:
    """The hypothesis ledger must expose its live experiment's maturity."""
    row = _digest()["experiment_queue"][0]
    row.update(
        {
            "configured_directions": ["long", "short"],
            "research_rank": 3,
            "prospective_observation": {"resolved_lifecycles": 0},
        }
    )

    hypothesis = continuous._hypothesis_record(
        row,
        {"confidence": "low", "evidence_source": "scorecard.json"},
        "v51",
    )

    assert hypothesis["prospective_observation"] == {"resolved_lifecycles": 0}


def _write_observer(tmp_path: Path, observed_at: datetime) -> Path:
    path = tmp_path / "observer.json"
    path.write_text(json.dumps(_observer_payload(observed_at)))
    return path


def _observer_payload(observed_at: datetime) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "v51_sol_route_native_one_blocker_shadow",
        "status": "candidate_lifecycle_pending",
        "observed_at_utc": observed_at.isoformat(),
        "capture_start_utc": "2026-08-15T10:00:00+00:00",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "source_run_id": "run-v51",
            "source_profile_id": "profile-v51",
            "source_profile_fingerprint": "a" * 64,
            "execution": {
                "strategy_id": "range_onset_bidirectional_v1",
                "symbol": "SOL",
            },
        },
        "coverage": {
            "raw_exact_evaluations": 65,
            "exact_candidates": 2,
            "attempts": 1,
            "resolved_executions": 0,
            "pending_or_unresolved": 1,
        },
        "attempts": [{"status": "exit_pending", "side": "short"}],
        "executions": [],
        "portfolio_journal": _portfolio_journal("deployable_flat_entry"),
    }


def _portfolio_journal(classification: str) -> dict[str, object]:
    deployable = int(classification == "deployable_flat_entry")
    existing = int(classification == "existing_symbol_position")
    return {
        "schema_version": 1,
        "mode": "candidate_portfolio_compatibility_journal",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "source_strategy_id": "range_onset_bidirectional_v1",
            "candidate_strategy_id": "sol_hourly_cross_relaxed_route_native_shadow_v1",
            "symbol": "SOL",
            "position_policy": "flat_entry_only",
            "maximum_positions": 10,
            "portfolio_pnl_claimed": False,
            "simulated_outcomes_are_non_additive": True,
        },
        "summary": {
            "attempts": 1,
            "deployable": deployable,
            "deployable_resolved": 0,
            "deployable_wins": 0,
            "deployable_losses": 0,
            "deployable_total_net_return_bps": 0,
            "deployable_profit_factor": None,
            "deployable_largest_abs_contribution_fraction": None,
            "deployable_active_pending": deployable,
            "deployable_technically_unresolved": 0,
            "deployable_observed_sides": ["short"] if deployable else [],
            "existing_symbol_position": existing,
            "portfolio_capacity": 0,
            "same_cycle_symbol_action": 0,
            "portfolio_state_unavailable": 0,
            "resolved": 0,
            "pending": 1,
        },
        "latest_attempts": [
            {
                "status": "exit_pending",
                "side": "short",
                "portfolio_classification": classification,
                "outcome_status": "pending_or_unresolved",
            }
        ],
    }


def _identity() -> ObserverIdentity:
    return ObserverIdentity("run-v51", "profile-v51", "a" * 64)


def _digest() -> dict[str, object]:
    return {
        "source": {
            "run_id": "run-v51",
            "profile_id": "profile-v51",
            "profile_fingerprint": "a" * 64,
        },
        "experiment_queue": [
            {
                "route": _ROUTE,
                "next_experiment": "collect_route_native_one_blocker_shadow",
                "independent_forward_paths": 0,
                "supporting_evidence": [],
            }
        ],
    }
