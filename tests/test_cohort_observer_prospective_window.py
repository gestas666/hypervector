"""Cutoff-bound evidence for a disarmed prospective observer."""

from __future__ import annotations

from copy import deepcopy

from hypervector.research.cohort_observer_prospective_window import (
    build_observer_prospective_window,
)

_RUN = "observer-run"
_PROFILE = "observer-profile"
_FINGERPRINT = "f" * 64
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_START_MS = 2_000


def test_window_excludes_pre_cutoff_decisions_and_preserves_authority_none() -> None:
    """Only frozen post-cutoff decisions may become prospective evidence."""
    rows = [
        _routing(1_500, _evaluation(1_500, eligible=True, side="short")),
        _routing(2_000, _evaluation(2_000, eligible=False, side="long")),
        _routing(3_000, _evaluation(3_000, eligible=True, side="long")),
    ]

    report = build_observer_prospective_window(
        rows,
        _full_audit(),
        start_ms=_START_MS,
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "profitability_measured": False,
        "runtime_strategy_changed": False,
    }
    assert report["window"]["start_ms"] == _START_MS
    assert report["window"]["pre_cutoff_evaluations_excluded"] == 1
    assert report["signals"]["evaluations"] == 2
    assert report["signals"]["eligible_evaluations"] == 1
    assert report["signals"]["by_side"] == {
        "long": {"eligible_evaluations": 1, "evaluations": 2}
    }
    assert report["technical"] == {
        "complete": True,
        "full_run_complete": True,
        "technical_gaps": [],
        "duplicate_evaluations": 0,
        "future_decisions": 0,
    }
    assert report["status"] == "prospective_eligible_signal_observed"


def test_window_reports_duplicate_and_future_decision_defects() -> None:
    """Duplicate keys and future decisions cannot become clean evidence."""
    duplicate = _evaluation(2_000, eligible=False, side="long")
    rows = [
        _routing(2_000, duplicate),
        _routing(2_000, deepcopy(duplicate)),
        _routing(4_000, _evaluation(5_000, eligible=False, side="short")),
    ]

    report = build_observer_prospective_window(
        rows,
        _full_audit(),
        start_ms=_START_MS,
    )

    assert report["technical"]["complete"] is False
    assert report["technical"]["duplicate_evaluations"] == 1
    assert report["technical"]["future_decisions"] == 1
    assert report["technical"]["technical_gaps"] == [
        "duplicate_evaluation_identity",
        "future_decision_timestamp",
    ]
    assert report["status"] == "technical_evidence_incomplete"


def test_window_carries_full_run_technical_failure_without_success_shaping() -> None:
    """A clean slice cannot conceal a broken observer run."""
    audit = _full_audit()
    audit["technical"] = {
        "complete": False,
        "technical_gaps": ["initial_candle_coverage_incomplete"],
    }

    report = build_observer_prospective_window(
        [_routing(2_000, _evaluation(2_000, eligible=False, side="long"))],
        audit,
        start_ms=_START_MS,
    )

    assert report["technical"]["complete"] is False
    assert report["technical"]["technical_gaps"] == [
        "full_run:initial_candle_coverage_incomplete"
    ]
    assert report["status"] == "technical_evidence_incomplete"


def test_window_reports_readiness_depth_without_claiming_independent_setups() -> None:
    """Repeated minute evaluations must expose proximity but not signal cadence."""
    rows = [
        _routing(2_000, _evaluation(2_000, eligible=False, side="long", met=0)),
        _routing(3_000, _evaluation(3_000, eligible=False, side="long", met=2)),
        _routing(4_000, _evaluation(4_000, eligible=False, side="long", met=2)),
    ]

    report = build_observer_prospective_window(rows, _full_audit(), start_ms=_START_MS)

    readiness = report["signals"]["readiness"]
    assert readiness["sampling_basis"] == "completed_minute_evaluations"
    assert readiness["independent_setup_count_claimed"] is False
    assert readiness["maximum_fraction"] == 2 / 3
    assert readiness["evaluations_at_maximum"] == 2
    assert readiness["fraction_distribution"] == [
        {"readiness_fraction": 0.0, "evaluations": 1},
        {"readiness_fraction": 2 / 3, "evaluations": 2},
    ]
    assert readiness["latest_at_maximum"] == {
        "decision_time_ms": 4_000,
        "side": "long",
        "conditions_met": 2,
        "conditions_required": 3,
        "blockers": ["canonical_breakout_onset_absent"],
        "reason": "canonical_breakout_onset_absent",
    }


def _full_audit() -> dict[str, object]:
    return {
        "observer_contract": {
            "report_only": True,
            "execution_authority": "none",
            "orders_observed": False,
            "fills_observed": False,
            "profitability_measured": False,
            "performance_gate": False,
            "runtime_strategy_changed": False,
        },
        "run": {
            "run_id": _RUN,
            "profile_id": _PROFILE,
            "profile_fingerprint": _FINGERPRINT,
        },
        "technical": {"complete": True, "technical_gaps": []},
        "signals": {"routed_actions": 0},
    }


def _routing(observed_ms: int, evaluation: dict[str, object]) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "observed_at_utc": f"1970-01-01T00:00:{observed_ms / 1000:06.3f}+00:00",
        "run_id": _RUN,
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "execution_mode": "observe",
        "live_armed": False,
        "execution_authority": "none",
        "payload": {"evaluations": [evaluation], "actions": [], "withheld": []},
    }


def _evaluation(
    decision_ms: int,
    *,
    eligible: bool,
    side: str,
    met: int = 2,
) -> dict[str, object]:
    return {
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "decision_time_ms": decision_ms,
        "eligible": eligible,
        "side": side,
        "reason": "canonical_breakout_onset_absent",
        "readiness": {
            "blockers": ["canonical_breakout_onset_absent"],
            "conditions_met": met,
            "conditions_required": 3,
            "readiness_fraction": met / 3,
        },
    }
