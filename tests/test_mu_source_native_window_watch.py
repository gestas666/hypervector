"""Prospective-only status for the independent MU lifecycle window."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.mu_source_native_window_watch import (
    build_mu_source_native_window_status,
)

_START_MS = 1_787_108_400_000
_DEADLINE_MS = 1_788_318_000_000


def test_status_excludes_pre_start_and_counts_exact_future_onsets() -> None:
    """Only preregistered prospective rows may enter the new sample."""
    rows = [
        _row(_START_MS - 900_000, eligible=True, side="long"),
        _row(_START_MS, eligible=True, side="long"),
        _row(_START_MS + 900_000, eligible=True, side="short"),
        _row(_START_MS + 1_800_000, eligible=False),
    ]

    status = build_mu_source_native_window_status(
        _preregistration(), rows, observed_at_ms=_START_MS + 2_000_000
    )

    assert status["included_decisions"] == 3
    assert status["eligible_onsets"] == 2
    assert status["eligible_onsets_by_side"] == {"long": 1, "short": 1}
    assert status["watch_state"] == "WAITING_ELIGIBLE_ONSET"
    assert status["collection_state"] == "collecting_minimum_onsets"
    assert status["lifecycle_replay_candidate_due"] is False
    assert status["execution_authority"] == "none"
    assert status["source"] == {"observed_decisions": 3, "eligible_decisions": 2}
    assert status["nominal"]["summary"]["resolved"] == 0
    assert status["technical_assessment"]["live_change_supported"] is False


def test_status_marks_candidate_only_after_frozen_both_side_minimum() -> None:
    """A pooled count cannot conceal absence of one configured side."""
    rows = [
        _row(_START_MS + index * 900_000, eligible=True, side=side)
        for index, side in enumerate(["long"] * 15 + ["short"] * 5)
    ]

    status = build_mu_source_native_window_status(
        _preregistration(), rows, observed_at_ms=_START_MS + 20 * 900_000
    )

    assert status["lifecycle_replay_candidate_due"] is True
    assert status["watch_state"] == "WAITING_ELIGIBLE_ONSET"
    assert status["collection_state"] == "lifecycle_replay_candidate_due"
    assert status["eligible_onsets"] == 20


def test_status_withholds_candidate_when_decision_schedule_has_a_gap() -> None:
    """A missing prospective boundary must remain an explicit technical failure."""
    rows = [
        _row(_START_MS + index * 900_000, eligible=True, side=side)
        for index, side in enumerate(["long"] * 15 + ["short"] * 6)
        if index != 7
    ]

    status = build_mu_source_native_window_status(
        _preregistration(),
        rows,
        observed_at_ms=_START_MS + 20 * 900_000 + 20_000,
    )

    assert status["eligible_onsets"] == 20
    assert status["lifecycle_replay_candidate_due"] is False
    assert status["watch_state"] == "TECHNICAL_COVERAGE_GAP"
    assert status["collection_state"] == "technical_coverage_gap"
    assert status["decision_coverage"] == {
        "expected_decisions": 21,
        "observed_decisions": 20,
        "complete": False,
        "latest_expected_decision_time_ms": _START_MS + 20 * 900_000,
        "missing_decision_time_ms": [_START_MS + 7 * 900_000],
        "grace_ms": 15_000,
    }
    assert status["technical_assessment"]["decision_schedule_complete"] is False


def test_status_rejects_nonprospective_included_decision() -> None:
    """Historical or bootstrap rows cannot be relabeled as future evidence."""
    row = _row(_START_MS, eligible=True, side="long")
    row["decision"]["prospective"] = False

    with pytest.raises(ValueError, match="must be prospective"):
        build_mu_source_native_window_status(
            _preregistration(), [row], observed_at_ms=_START_MS + 1
        )


def test_status_rejects_wrong_route_identity_and_duplicate_boundary() -> None:
    """Aliased identities and duplicate decisions fail closed."""
    wrong = _row(_START_MS, eligible=True, side="long")
    wrong["decision"]["symbol"] = "xyz:SP500"
    with pytest.raises(ValueError, match="identity"):
        build_mu_source_native_window_status(
            _preregistration(), [wrong], observed_at_ms=_START_MS + 1
        )

    exact = _row(_START_MS, eligible=False)
    with pytest.raises(ValueError, match="duplicate"):
        build_mu_source_native_window_status(
            _preregistration(),
            [exact, deepcopy(exact)],
            observed_at_ms=_START_MS + 3_000,
        )


def _preregistration() -> dict[str, object]:
    return {
        "schema_version": "v57_mu_source_native_independent_window_preregistration_v1",
        "status": "prospective_collecting",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "independence_contract": {"decision_start_ms": _START_MS},
        "frozen_strategy_contract": {
            "symbol": "xyz:MU",
            "provider_id": "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
            "profile_id": "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
            "maximum_book_lateness_ms": 15_000,
        },
        "stopping_rule": {
            "minimum_eligible_onsets_before_replay": 20,
            "minimum_eligible_onsets_per_side_before_replay": 5,
            "time_limit_ms": _DEADLINE_MS,
        },
    }


def _row(
    decision_time_ms: int,
    *,
    eligible: bool,
    side: str | None = None,
) -> dict[str, object]:
    return {
        "event_type": "mu_hip3_breakout_shadow_decision",
        "decision": {
            "symbol": "xyz:MU",
            "provider_id": "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
            "profile_id": "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
            "decision_time_ms": decision_time_ms,
            "observed_at_ms": decision_time_ms + 2_000,
            "eligible": eligible,
            "side": side,
            "prospective": True,
            "execution_authority": "none",
        },
    }
