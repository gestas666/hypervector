"""Side-aware reconciliation tests for exact route lifecycle evidence."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.cohort_route_lifecycle_side_reconciliation import (
    reconcile_route_lifecycle_sides,
)


_ROUTE = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX"
_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_FINGERPRINT = "8" * 64
_RUN = "bidirectional-live-1787166474078"


def test_observe_only_long_does_not_become_unattributed_short_evidence() -> None:
    """An excluded long setup must leave an exact short-only route awaiting short."""
    report = reconcile_route_lifecycle_sides(_status(), _checkpoint())

    assert report["state"] == "awaiting_short"
    assert report["side_eligibility"] == {
        "prospective_by_side": {"long": 1, "short": 0},
        "executable_side_eligible_evaluations": 0,
        "excluded_side_eligible_evaluations": 1,
        "attributable_executable_lifecycles": 0,
        "unattributed_executable_side_eligible_evaluations": 0,
    }
    assert report["contract"]["execution_authority"] == "none"
    assert report["live_change_supported"] is False


def test_required_short_without_lifecycle_remains_unattributed() -> None:
    """An executable short setup still requires an attributable lifecycle."""
    checkpoint = _checkpoint()
    outcomes = checkpoint["audit"]["signal_outcomes"]["by_provider_symbol"][_ROUTE]
    outcomes["by_side"]["long"]["eligible_evaluations"] = 0
    outcomes["by_side"]["short"]["eligible_evaluations"] = 1

    report = reconcile_route_lifecycle_sides(_status(), checkpoint)

    assert report["state"] == "eligible_evidence_unattributed"
    assert (
        report["side_eligibility"]["unattributed_executable_side_eligible_evaluations"]
        == 1
    )


def test_nonzero_eligible_baseline_fails_closed() -> None:
    """Cumulative side counts cannot be assigned across an unknown side baseline."""
    status = _status()
    status["prospective_boundary"]["baseline_eligible"] = 1

    with pytest.raises(ValueError, match="zero eligible baseline"):
        reconcile_route_lifecycle_sides(status, _checkpoint())


def test_inconsistent_signal_side_counts_fail_closed() -> None:
    """Side attribution must exactly reconcile to the aggregate eligible count."""
    checkpoint = deepcopy(_checkpoint())
    outcomes = checkpoint["audit"]["signal_outcomes"]["by_provider_symbol"][_ROUTE]
    outcomes["by_side"]["short"]["eligible_evaluations"] = 1

    with pytest.raises(ValueError, match="side counts do not reconcile"):
        reconcile_route_lifecycle_sides(_status(), checkpoint)


def _status() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_exact_route_lifecycle_evidence",
        "observed_at_utc": "2026-08-20T16:39:36+00:00",
        "state": "eligible_evidence_unattributed",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "identity": _identity(),
        "prospective_boundary": {
            "capture_start_ms": 1,
            "baseline_evaluations": 62,
            "baseline_eligible": 0,
        },
        "route_readiness": {
            "evaluations": 87,
            "eligible": 1,
            "prospective_evaluations": 25,
            "prospective_eligible": 1,
            "unattributed_eligible_evaluations": 1,
        },
        "side_progress": {"short": _pending_progress()},
        "open_lifecycles": [],
        "closed_lifecycles": [],
        "resolved_lifecycles": [],
        "unresolved_lifecycles": [],
        "minimum_diagnostic_evidence_met": False,
        "live_change_supported": False,
    }


def _identity() -> dict[str, object]:
    return {
        "run_id": _RUN,
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "provider_id": _ROUTE.split("|")[0],
        "signal_strategy_id": _ROUTE.split("|")[0],
        "symbol": "xyz:SPCX",
        "route": _ROUTE,
        "required_sides": ["short"],
    }


def _pending_progress() -> dict[str, object]:
    return {
        "attributable_entries": 0,
        "open_lifecycles": 0,
        "closed_lifecycles": 0,
        "resolved_lifecycles": 0,
        "minimum_met": False,
    }


def _checkpoint() -> dict[str, object]:
    contract = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    return {
        "generated_at_utc": "2026-08-20T16:41:40+00:00",
        "checkpoint_contract": contract,
        "configuration_generation": {
            "matches_runtime": True,
            "current_profile_fingerprint": _FINGERPRINT,
            "runtime_profile_fingerprint": _FINGERPRINT,
            "current_provider_execution_directions": {_ROUTE: ["short"]},
        },
        "audit": {
            "experiment_contract": contract,
            "run": {
                "run_id": _RUN,
                "profile_id": _PROFILE,
                "profile_fingerprint": _FINGERPRINT,
            },
            "readiness": {
                "by_provider_symbol": {
                    _ROUTE: {"count": 87, "eligible": 1},
                }
            },
            "signal_outcomes": {
                "by_provider_symbol": {
                    _ROUTE: {
                        "eligible_evaluations": 1,
                        "by_side": {
                            "long": {"eligible_evaluations": 1},
                            "short": {"eligible_evaluations": 0},
                        },
                    }
                }
            },
        },
    }
