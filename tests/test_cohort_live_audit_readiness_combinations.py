"""Exact blocker-combination coverage for live readiness summaries."""

from __future__ import annotations

from hypervector.research.cohort_live_audit_summaries import readiness_summary


def test_readiness_preserves_exact_blocker_combinations() -> None:
    """Separate blocker counts must not conceal simultaneous failed conditions."""
    report = readiness_summary(_records(), _identity())

    route = report["by_provider_symbol"]["range|SOL"]
    assert route["blocker_combinations"] == [
        {"blockers": [], "evaluations": 1},
        {"blockers": ["cross_absent"], "evaluations": 1},
        {"blockers": ["cross_absent", "regime_blocked"], "evaluations": 2},
    ]


def _records() -> list[dict[str, object]]:
    combinations = [
        ["regime_blocked", "cross_absent"],
        ["cross_absent"],
        ["cross_absent", "regime_blocked"],
        [],
    ]
    evaluations = [_evaluation(blockers) for blockers in combinations]
    return [{"event_type": "intent_routing", "payload": {"evaluations": evaluations}}]


def _evaluation(blockers: list[str]) -> dict[str, object]:
    return {
        "strategy_id": "range",
        "symbol": "SOL",
        "eligible": not blockers,
        "reason": "eligible" if not blockers else "no_trigger",
        "readiness": {
            "readiness_fraction": 1.0 if not blockers else 0.5,
            "side": "long",
            "blockers": blockers,
            "indicators": [],
            "metrics": {},
        },
    }


def _identity() -> dict[str, object]:
    return {
        "payload": {
            "providers": [
                {
                    "strategy_id": "range",
                    "symbols": ["SOL"],
                    "execution_symbols": ["SOL"],
                }
            ]
        }
    }
