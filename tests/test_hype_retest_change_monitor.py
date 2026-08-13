"""Tests for before/after monitoring of the HYPE retest revision."""

from __future__ import annotations

from hypervector.research.hype_retest_change_monitor import (
    build_hype_retest_change_monitor,
)

_V1 = "hype_breakout_onset_bidirectional_v1"
_V2 = "hype_breakout_retest_bidirectional_v2"


def _evaluation(
    strategy: str,
    decision_time_ms: int,
    *,
    eligible: bool,
    side: str,
    onset: bool,
    state: str | None,
    breakout_side: str,
    structural_side: str | None = None,
    entry_mode: str | None = None,
) -> dict[str, object]:
    metrics: dict[str, object] = {
        "breakout_onset": onset,
        "breakout_side": breakout_side,
    }
    if state is not None:
        metrics["entry_policy_state"] = state
    if structural_side is not None:
        metrics["structural_direction"] = structural_side
    if entry_mode is not None:
        metrics["entry_mode"] = entry_mode
    return {
        "strategy_id": strategy,
        "symbol": "HYPE",
        "decision_time_ms": decision_time_ms,
        "eligible": eligible,
        "side": side,
        "reason": "fixture",
        "readiness": {"metrics": metrics},
    }


def _routing(*evaluations: dict[str, object]) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "run_id": "run-v13",
        "payload": {"evaluations": list(evaluations)},
    }


def test_monitor_matches_v1_onset_to_v2_arm_and_confirmation() -> None:
    """The change report preserves the control decision and revised lifecycle."""
    onset_ms = 1_000_000
    report = build_hype_retest_change_monitor(
        (
            _routing(
                _evaluation(
                    _V1,
                    onset_ms,
                    eligible=True,
                    side="long",
                    onset=True,
                    state=None,
                    breakout_side="short",
                ),
                _evaluation(
                    _V2,
                    onset_ms,
                    eligible=False,
                    side="short",
                    onset=True,
                    state="armed",
                    breakout_side="short",
                ),
            ),
            _routing(
                _evaluation(
                    _V2,
                    onset_ms + 60_000,
                    eligible=True,
                    side="short",
                    onset=False,
                    state="confirmed",
                    breakout_side="short",
                )
            ),
        )
    )

    assert report["status"] == "contract_consistent"
    assert report["control_onsets"] == 1
    assert report["retest_armed"] == 1
    assert report["retest_confirmed"] == 1
    assert report["retest_expired"] == 0
    assert report["hard_invariant_violations"] == []
    assert report["matched_onsets"][0]["v1_side"] == "long"
    assert report["matched_onsets"][0]["v2_side"] == "short"
    assert report["matched_onsets"][0]["breakout_side"] == "short"


def test_monitor_surfaces_immediate_or_wrong_side_execution_as_fault() -> None:
    """A success-shaped v2 evaluation outside confirmation is a visible defect."""
    report = build_hype_retest_change_monitor(
        (
            _routing(
                _evaluation(
                    _V2,
                    1_000_000,
                    eligible=True,
                    side="long",
                    onset=True,
                    state="armed",
                    breakout_side="short",
                )
            ),
        )
    )

    assert report["status"] == "technical_fault"
    assert report["hard_invariant_violations"] == [
        {
            "decision_time_ms": 1_000_000,
            "reasons": [
                "eligible_without_confirmation",
                "eligible_on_immediate_onset",
                "eligible_side_opposes_breakout",
            ],
            "side": "long",
            "breakout_side": "short",
        }
    ]


def test_monitor_accepts_confirmed_opposed_structural_fade() -> None:
    """A confirmed fade must use structural side opposite the breakout side."""
    report = build_hype_retest_change_monitor(
        (
            _routing(
                _evaluation(
                    _V2,
                    1_060_000,
                    eligible=True,
                    side="long",
                    onset=False,
                    state="confirmed",
                    breakout_side="short",
                    structural_side="long",
                    entry_mode="fade",
                )
            ),
        )
    )

    assert report["status"] == "contract_consistent"
    assert report["retest_confirmed"] == 1
    assert report["hard_invariant_violations"] == []
