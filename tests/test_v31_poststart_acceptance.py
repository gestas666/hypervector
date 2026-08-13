"""Technical acceptance contracts for the first exact v31 checkpoint."""

from __future__ import annotations

from copy import deepcopy

from hypervector.research.v31_poststart_acceptance import (
    PRESSURE_ROUTES,
    build_candidate_poststart_acceptance,
    build_v31_poststart_acceptance,
)
from hypervector.research.v32_acceptance import build_v32_poststart_acceptance

_V32_PROFILE = "multi_asset_bidirectional_commodity_swing_retired_candidate_v32"


def test_complete_v31_checkpoint_is_technically_accepted() -> None:
    report = build_v31_poststart_acceptance(_checkpoint(), _route_snapshot())

    assert report["accepted"] is True
    assert report["decision"] == "accepted"
    assert report["reasons"] == []
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_transition": False,
        "runtime_strategy_changed": False,
    }
    pressure = report["checks"]["hip3_pressure_telemetry"]
    assert pressure["passed"] is True
    assert set(pressure["routes"]) == set(PRESSURE_ROUTES)


def test_source_identity_and_incomplete_coverage_are_rejected() -> None:
    checkpoint = _checkpoint()
    checkpoint["audit"]["coverage"] = {
        "complete": False,
        "technical_gaps": ["provider_metric_telemetry_missing"],
    }
    snapshot = _route_snapshot()
    snapshot["phase"] = "pretransition_v25_baseline"

    report = build_v31_poststart_acceptance(checkpoint, snapshot)

    assert report["accepted"] is False
    assert report["decision"] == "rejected"
    assert "candidate_identity_not_active" in report["reasons"]
    assert "audit_coverage_incomplete" in report["reasons"]


def test_missing_and_stale_pressure_are_rejected_per_route() -> None:
    checkpoint = _checkpoint()
    first, second = PRESSURE_ROUTES[:2]
    diagnostics = _diagnostics(checkpoint, first)
    diagnostics["metrics"]["imbalance_10"]["missing_evaluations"] = 1
    diagnostics["coverage"]["complete"] = False
    diagnostics["coverage"]["metric_value_gaps"] = 1
    _diagnostics(checkpoint, second)["metrics"]["pressure_age_seconds"]["maximum"] = (
        30.001
    )

    report = build_v31_poststart_acceptance(checkpoint, _route_snapshot())

    assert report["accepted"] is False
    assert f"pressure_metric_incomplete:{first}:imbalance_10" in report["reasons"]
    assert f"pressure_age_out_of_bounds:{second}" in report["reasons"]


def test_fault_or_unprotected_position_is_rejected() -> None:
    checkpoint = _checkpoint()
    checkpoint["audit"]["health"]["faults"] = 1
    snapshot = _route_snapshot()
    snapshot["live_state"]["all_open_positions_protected"] = False
    snapshot["live_state"]["open_positions"][0]["protected_if_open"] = False

    report = build_v31_poststart_acceptance(checkpoint, snapshot)

    assert report["accepted"] is False
    assert "runtime_faults_present" in report["reasons"]
    assert "open_position_unprotected" in report["reasons"]


def test_builder_does_not_mutate_acceptance_inputs() -> None:
    checkpoint, snapshot = _checkpoint(), _route_snapshot()
    original_checkpoint, original_snapshot = deepcopy(checkpoint), deepcopy(snapshot)

    build_v31_poststart_acceptance(checkpoint, snapshot)

    assert checkpoint == original_checkpoint
    assert snapshot == original_snapshot


def test_v32_identity_is_accepted_only_by_exact_candidate_specification() -> None:
    snapshot = _route_snapshot()
    snapshot["phase"] = "candidate_v32_forward"
    snapshot["source_run"]["profile_id"] = _V32_PROFILE
    snapshot["candidate"]["profile_id"] = _V32_PROFILE

    report = build_candidate_poststart_acceptance(
        _checkpoint(),
        snapshot,
        expected_profile_id=_V32_PROFILE,
        expected_phase="candidate_v32_forward",
        schema_version="v32_poststart_acceptance_v1",
    )
    v31_report = build_v31_poststart_acceptance(_checkpoint(), snapshot)

    assert report["accepted"] is True
    assert report["schema_version"] == "v32_poststart_acceptance_v1"
    assert v31_report["accepted"] is False
    assert "candidate_identity_not_active" in v31_report["reasons"]


def test_candidate_acceptance_rejects_wrong_phase_for_matching_profile() -> None:
    snapshot = _route_snapshot()
    snapshot["source_run"]["profile_id"] = _V32_PROFILE
    snapshot["candidate"]["profile_id"] = _V32_PROFILE

    report = build_candidate_poststart_acceptance(
        _checkpoint(),
        snapshot,
        expected_profile_id=_V32_PROFILE,
        expected_phase="candidate_v32_forward",
        schema_version="v32_poststart_acceptance_v1",
    )

    assert report["accepted"] is False
    assert "candidate_identity_not_active" in report["reasons"]


def test_named_v32_poststart_builder_binds_exact_schema_and_identity() -> None:
    snapshot = _route_snapshot()
    snapshot["phase"] = "candidate_v32_forward"
    snapshot["source_run"]["profile_id"] = _V32_PROFILE
    snapshot["candidate"]["profile_id"] = _V32_PROFILE

    report = build_v32_poststart_acceptance(_checkpoint(), snapshot)

    assert report["accepted"] is True
    assert report["schema_version"] == "v32_poststart_acceptance_v1"


def _checkpoint() -> dict[str, object]:
    outcomes = {route: _outcome() for route in PRESSURE_ROUTES}
    return {
        "generated_at_utc": "2026-08-09T20:00:00+00:00",
        "transition_drain": {"status": "inactive"},
        "audit": {
            "coverage": {"complete": True, "technical_gaps": []},
            "health": {"faults": 0},
            "signal_outcomes": {
                "coverage": {
                    "complete": True,
                    "market_data_complete": True,
                    "metric_telemetry_complete": True,
                    "evaluations_without_metrics": 0,
                    "metric_value_gaps": 0,
                },
                "by_provider_symbol": outcomes,
            },
        },
    }


def _outcome() -> dict[str, object]:
    return {
        "evaluations": 2,
        "metric_diagnostics": {
            "coverage": {
                "complete": True,
                "evaluations_with_metrics": 2,
                "evaluations_without_metrics": 0,
                "metric_value_gaps": 0,
            },
            "metrics": {
                "imbalance_10": _metric(-0.4, 0.1, 0.5),
                "pressure_age_seconds": _metric(0.002, 5.0, 12.0),
            },
        },
    }


def _metric(minimum: float, mean: float, maximum: float) -> dict[str, object]:
    return {
        "kind": "numeric",
        "value_type": "float",
        "observations": 2,
        "missing_evaluations": 0,
        "minimum": minimum,
        "mean": mean,
        "maximum": maximum,
        "horizons": {},
    }


def _route_snapshot() -> dict[str, object]:
    return {
        "phase": "candidate_v31_forward",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_transition": False,
            "runtime_strategy_changed": False,
        },
        "source_run": {
            "run_id": "v31-live-run",
            "profile_id": "multi_asset_bidirectional_swing_pruned_candidate_v31",
            "profile_fingerprint": "candidate-fingerprint",
        },
        "candidate": {
            "profile_id": "multi_asset_bidirectional_swing_pruned_candidate_v31",
            "profile_fingerprint": "candidate-fingerprint",
            "both_directions": True,
        },
        "live_state": {
            "faults": 0,
            "all_open_positions_protected": True,
            "open_positions": [
                {"symbol": "ETH", "protected_if_open": True, "stop_oid": 123}
            ],
        },
    }


def _diagnostics(checkpoint: dict[str, object], route: str) -> dict[str, object]:
    return checkpoint["audit"]["signal_outcomes"]["by_provider_symbol"][route][
        "metric_diagnostics"
    ]
