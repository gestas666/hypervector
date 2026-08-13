"""Causal maximum-hold decision projection tests."""

from __future__ import annotations

from hypervector.research.cohort_maximum_hold_decisions import (
    build_maximum_hold_decision_evidence,
)


def test_terminal_exit_is_reported_without_double_counting_soft_boundary() -> None:
    """One lifecycle exposes its soft extension and later terminal exit."""
    soft = _payload(
        decision_id="HYPE:99:soft_maximum_hold",
        decision_stage="soft",
        decision_time_ms=29_800_000,
        outcome="extend",
        exit_reason=None,
    )
    terminal = _payload(
        decision_id="HYPE:99:terminal_maximum_hold",
        decision_stage="terminal",
        decision_time_ms=29_860_000,
        outcome="exit",
        exit_reason="maximum_hold_seconds",
    ) | {
        "trigger_decision_id": "HYPE:99:soft_maximum_hold",
        "extension_duration_ms": 60_000,
    }

    evidence = build_maximum_hold_decision_evidence(
        [_record(soft), _record(terminal)],
        frozenset({"hype|HYPE"}),
    )

    assert evidence["summary"] == {
        "observed": 1,
        "extended": 1,
        "exited": 0,
        "provider_symbols": 1,
    }
    assert evidence["terminal_exit_summary"] == {
        "observed": 1,
        "provider_symbols": 1,
        "by_exit_reason": {"maximum_hold_seconds": 1},
    }
    assert evidence["latest_terminal_exits"] == [terminal]


def test_namespaced_symbol_lifecycle_identity_is_valid() -> None:
    """HIP-3 symbols may contain colons without invalidating their lifecycle."""
    payload = _payload(
        decision_id="xyz:GOLD:123:soft_maximum_hold",
        decision_stage="soft",
        decision_time_ms=29_800_000,
        outcome="exit",
        exit_reason="maximum_hold_seconds",
    ) | {
        "lifecycle_id": "xyz:GOLD:123",
        "symbol": "xyz:GOLD",
        "strategy_id": "hip3_swing",
    }

    evidence = build_maximum_hold_decision_evidence(
        [_record(payload)],
        frozenset({"hip3_swing|xyz:GOLD"}),
    )

    assert evidence["latest_decisions"] == [payload]


def _payload(
    *,
    decision_id: str,
    decision_stage: str,
    decision_time_ms: int,
    outcome: str,
    exit_reason: str | None,
) -> dict[str, object]:
    return {
        "decision_id": decision_id,
        "decision_stage": decision_stage,
        "lifecycle_id": "HYPE:99",
        "symbol": "HYPE",
        "strategy_id": "hype",
        "side": "long",
        "decision_time_ms": decision_time_ms,
        "opened_at_ms": 1_000_000,
        "elapsed_ms": decision_time_ms - 1_000_000,
        "soft_deadline_timestamp_ms": 29_800_000,
        "hard_deadline_timestamp_ms": 87_400_000,
        "outcome": outcome,
        "exit_reason": exit_reason,
        "structure_alignment_score": 0.75 if outcome == "extend" else 0.25,
        "structure_alignment_threshold": 0.5,
        "provider_evaluation": None,
        "canonical_evaluation": None,
    }


def _record(payload: dict[str, object]) -> dict[str, object]:
    return {"event_type": "maximum_hold_decision", "payload": payload}
