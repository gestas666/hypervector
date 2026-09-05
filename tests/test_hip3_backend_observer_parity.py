"""Exact active-backend versus independent HIP-3 observer parity tests."""

from __future__ import annotations

import importlib
from typing import Callable


def test_matching_current_run_rows_resolve_backend_observer_parity() -> None:
    """Every common decision field must reconcile on a complete 15m window."""
    build = _builder()
    rows = (
        _cohort_row(900_000, "xyz:SP500", imbalance=0.25),
        _cohort_row(1_800_000, "xyz:SP500", imbalance=-0.10),
        _cohort_row(900_000, "xyz:SPCX", imbalance=-0.30),
        _cohort_row(1_800_000, "xyz:SPCX", imbalance=0.12),
    )
    observers = {
        "xyz:SP500": (
            _observer_row(900_000, "xyz:SP500", imbalance=0.25),
            _observer_row(1_800_000, "xyz:SP500", imbalance=-0.10),
        ),
        "xyz:SPCX": (
            _observer_row(900_000, "xyz:SPCX", imbalance=-0.30),
            _observer_row(1_800_000, "xyz:SPCX", imbalance=0.12),
        ),
    }

    report = build(
        cohort_rows=rows,
        observer_rows_by_symbol=observers,
        run_id="live-run",
        profile_id="v51",
        profile_fingerprint="fingerprint",
        provider_id="index-v3",
        symbols=("xyz:SP500", "xyz:SPCX"),
        run_started_at_ms=1,
    )

    _assert_matching_report(report)


def _assert_matching_report(report: dict[str, object]) -> None:
    """Assert the complete resolved-report contract."""

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    assert report["coverage"] == {
        "comparison_start_ms": 900_000,
        "comparison_end_ms": 1_800_000,
        "decisions_per_symbol": 2,
        "backend_decisions": 4,
        "observer_decisions": 4,
        "excluded_later_backend_decisions": 0,
        "excluded_later_observer_decisions": 0,
        "backend_technical_unavailable_evaluations": 0,
        "backend_technical_unavailable_by_symbol": {},
        "backend_technical_unavailable_by_reason": {},
    }
    assert report["decision_diagnostics"] == []
    assert report["technical_assessment"] == {
        "backend_observer_decision_parity_resolved": True,
        "expected_decisions": 4,
        "compared_decisions": 4,
        "mismatches": 0,
    }


def test_changed_pressure_is_serialized_as_an_exact_field_mismatch() -> None:
    """A shared boundary with different evidence must remain inspectable."""
    report = _builder()(
        cohort_rows=(_cohort_row(900_000, "xyz:SP500", imbalance=0.25),),
        observer_rows_by_symbol={
            "xyz:SP500": (_observer_row(900_000, "xyz:SP500", imbalance=-0.25),)
        },
        run_id="live-run",
        profile_id="v51",
        profile_fingerprint="fingerprint",
        provider_id="index-v3",
        symbols=("xyz:SP500",),
        run_started_at_ms=1,
    )

    diagnostics = report["decision_diagnostics"]
    assert isinstance(diagnostics, list)
    assert diagnostics == [
        {
            "symbol": "xyz:SP500",
            "decision_time_ms": 900_000,
            "reason": "field_mismatch",
            "differing_fields": ["imbalance_10"],
            "backend": {
                "imbalance_10": 0.25,
            },
            "observer": {
                "imbalance_10": -0.25,
            },
        }
    ]
    assert report["technical_assessment"] == {
        "backend_observer_decision_parity_resolved": False,
        "expected_decisions": 1,
        "compared_decisions": 1,
        "mismatches": 1,
    }


def test_missing_internal_observer_boundary_is_not_hidden_by_common_cutoff() -> None:
    """A gap inside the shared interval must fail parity with its exact identity."""
    backend = tuple(
        _cohort_row(time, "xyz:SP500", imbalance=0.25)
        for time in (900_000, 1_800_000, 2_700_000)
    )
    observer = tuple(
        _observer_row(time, "xyz:SP500", imbalance=0.25)
        for time in (900_000, 2_700_000)
    )

    report = _builder()(
        cohort_rows=backend,
        observer_rows_by_symbol={"xyz:SP500": observer},
        run_id="live-run",
        profile_id="v51",
        profile_fingerprint="fingerprint",
        provider_id="index-v3",
        symbols=("xyz:SP500",),
        run_started_at_ms=1,
    )

    assert report["coverage"]["backend_decisions"] == 3
    assert report["coverage"]["observer_decisions"] == 2
    diagnostics = report["decision_diagnostics"]
    assert isinstance(diagnostics, list)
    assert len(diagnostics) == 1
    assert diagnostics[0]["symbol"] == "xyz:SP500"
    assert diagnostics[0]["decision_time_ms"] == 1_800_000
    assert diagnostics[0]["reason"] == "missing_observer"
    assert diagnostics[0]["backend"]["imbalance_10"] == 0.25
    assert diagnostics[0]["observer"] is None
    assert (
        report["technical_assessment"]["backend_observer_decision_parity_resolved"]
        is False
    )


def test_interbar_technical_unavailability_is_counted_not_parsed_as_decision() -> None:
    """Fail-closed status polls must not masquerade as completed decisions."""
    report = _builder()(
        cohort_rows=(
            _unavailable_cohort_row(1_100_000, "xyz:SP500"),
            _cohort_row(1_800_000, "xyz:SP500", imbalance=0.25),
        ),
        observer_rows_by_symbol={
            "xyz:SP500": (_observer_row(1_800_000, "xyz:SP500", imbalance=0.25),)
        },
        run_id="live-run",
        profile_id="v51",
        profile_fingerprint="fingerprint",
        provider_id="index-v3",
        symbols=("xyz:SP500",),
        run_started_at_ms=1,
    )

    assert report["technical_assessment"] == {
        "backend_observer_decision_parity_resolved": True,
        "expected_decisions": 1,
        "compared_decisions": 1,
        "mismatches": 0,
    }
    assert report["coverage"]["backend_technical_unavailable_evaluations"] == 1
    assert report["coverage"]["backend_technical_unavailable_by_symbol"] == {
        "xyz:SP500": 1
    }
    assert report["coverage"]["backend_technical_unavailable_by_reason"] == {
        "observer_status_stale": 1
    }


def test_shared_internal_boundary_gap_is_not_treated_as_compared_parity() -> None:
    """A matching absence in both sources is unresolved coverage, not equality."""
    times = (900_000, 2_700_000)
    report = _builder()(
        cohort_rows=tuple(
            _cohort_row(time, "xyz:SP500", imbalance=0.25) for time in times
        ),
        observer_rows_by_symbol={
            "xyz:SP500": tuple(
                _observer_row(time, "xyz:SP500", imbalance=0.25) for time in times
            )
        },
        run_id="live-run",
        profile_id="v51",
        profile_fingerprint="fingerprint",
        provider_id="index-v3",
        symbols=("xyz:SP500",),
        run_started_at_ms=1,
    )

    assert report["decision_diagnostics"] == [
        {
            "symbol": "xyz:SP500",
            "decision_time_ms": 1_800_000,
            "reason": "missing_both",
            "backend": None,
            "observer": None,
        }
    ]
    assert report["technical_assessment"] == {
        "backend_observer_decision_parity_resolved": False,
        "expected_decisions": 3,
        "compared_decisions": 2,
        "mismatches": 1,
    }


def _builder() -> Callable[..., dict[str, object]]:
    module = importlib.import_module(
        "hypervector.research.hip3_backend_observer_parity"
    )
    return module.build_hip3_backend_observer_parity


def _cohort_row(
    decision_time_ms: int, symbol: str, *, imbalance: float
) -> dict[str, object]:
    evaluation = {
        "strategy_id": "index-v3",
        "symbol": symbol,
        "decision_time_ms": decision_time_ms,
        "eligible": False,
        "side": None,
        "readiness": {
            "metrics": {
                "decision_delay_ms": 2_000,
                "imbalance_10": imbalance,
                "pressure_boundary_age_ms": 3_000,
                "pressure_snapshot_count": 120,
                "pressure_history_complete": True,
                "pressure_scan_complete": True,
                "pressure_source": "hyperliquid_mainnet_l2_rest",
            }
        },
    }
    return {
        "event_type": "intent_routing",
        "run_id": "live-run",
        "profile_id": "v51",
        "profile_fingerprint": "fingerprint",
        "live_armed": True,
        "payload": {"evaluations": [evaluation]},
    }


def _unavailable_cohort_row(decision_time_ms: int, symbol: str) -> dict[str, object]:
    evaluation = {
        "strategy_id": "index-v3",
        "symbol": symbol,
        "decision_time_ms": decision_time_ms,
        "decision_action": "technical_unavailable",
        "eligible": False,
        "side": None,
        "reason": "observer_status_stale",
        "backend_non_action_reason": "observer_status_stale",
        "readiness": {
            "conditions_met": 0,
            "conditions_required": 1,
            "blockers": ["observer_status_stale"],
            "metrics": {"technical_availability": "unavailable"},
        },
    }
    return {
        "event_type": "intent_routing",
        "run_id": "live-run",
        "profile_id": "v51",
        "profile_fingerprint": "fingerprint",
        "live_armed": True,
        "payload": {"evaluations": [evaluation]},
    }


def _observer_row(
    decision_time_ms: int, symbol: str, *, imbalance: float
) -> dict[str, object]:
    return {
        "event_type": "index_hip3_breakout_shadow_decision",
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "intents": [],
        "decision": {
            "provider_id": "index-v3",
            "symbol": symbol,
            "decision_time_ms": decision_time_ms,
            "eligible": False,
            "side": None,
            "decision_delay_ms": 2_000,
            "decision_imbalance_10": imbalance,
            "pressure_end_boundary_age_ms": 3_000,
            "pressure_snapshot_count": 120,
            "pressure_state_history_complete": True,
            "pressure_scan_complete": True,
            "pressure_source": "hyperliquid_mainnet_l2_rest",
            "prospective": True,
            "execution_authority": "none",
        },
    }
