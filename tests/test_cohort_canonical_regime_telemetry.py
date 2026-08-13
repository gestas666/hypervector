"""Canonical regime projection into report-only cohort audits."""

from __future__ import annotations

from hypervector.research.cohort_canonical_regime_telemetry import (
    build_canonical_regime_telemetry_summary,
)


def test_summary_retains_latest_causal_row_from_recovery_batch() -> None:
    """A recovery event exposes the latest distinct close without losing history."""
    report = build_canonical_regime_telemetry_summary(
        [
            _row(
                "2026-08-11T04:03:05+00:00",
                [_evaluation(1_786_420_920_000), _evaluation(1_786_420_980_000)],
            )
        ]
    )

    assert report["evaluations"] == 2
    assert report["symbols"] == 1
    btc = report["by_symbol"]["BTC"]
    assert btc["evaluations"] == 2
    assert btc["latest_observed_at_utc"] == "2026-08-11T04:03:05+00:00"
    assert btc["latest"]["decision_time_ms"] == 1_786_420_980_000


def _row(observed: str, evaluations: list[dict[str, object]]) -> dict[str, object]:
    return {
        "event_type": "canonical_regime_evaluations",
        "observed_at_utc": observed,
        "payload": {
            "contract": {
                "execution_authority": "none",
                "intents_emitted": False,
                "configured_route": False,
            },
            "evaluations": evaluations,
        },
    }


def _evaluation(decision_time_ms: int) -> dict[str, object]:
    return {
        "strategy_id": "canonical_regime_telemetry_v1",
        "symbol": "BTC",
        "decision_time_ms": decision_time_ms,
        "reference_price": 100.0,
        "decision_action": "regime_observation",
        "eligible": False,
        "reason": "canonical_regime_observation",
        "side": None,
        "primary_regime": "RANGE",
        "state_1m": "RANGE",
        "state_5m": "RANGE",
        "context_15m": "RANGE",
        "confidence": 0.5,
        "backend_non_action_reason": "telemetry_only_no_execution_authority",
        "readiness": {"metrics": {"structural_direction": "neutral"}},
    }
