"""Startup readiness retains exact non-action metrics for acceptance."""

from hypervector.research.cohort_live_audit_summaries import readiness_summary


def test_readiness_summary_retains_latest_metrics_and_backend_reason() -> None:
    """A causal startup seed remains inspectable without becoming a trade signal."""
    identity = {
        "payload": {
            "providers": [{"strategy_id": "pressure_v3", "symbols": ["xyz:SP500"]}]
        }
    }
    records = [
        {
            "event_type": "intent_routing",
            "payload": {
                "evaluations": [
                    {
                        "strategy_id": "pressure_v3",
                        "symbol": "xyz:SP500",
                        "eligible": False,
                        "reason": "fresh_breakout_onset_absent",
                        "backend_non_action_reason": "pre_activation_readiness_seed",
                        "readiness": {
                            "readiness_fraction": 0.8,
                            "side": None,
                            "blockers": ["fresh_breakout_onset_absent"],
                            "indicators": ["L2 STATUS FRESH"],
                            "metrics": {
                                "pressure_status": "available",
                                "pressure_age_seconds": 1.5,
                            },
                        },
                    }
                ]
            },
        }
    ]

    route = readiness_summary(records, identity)["by_provider_symbol"][
        "pressure_v3|xyz:SP500"
    ]

    assert route["latest_backend_non_action_reason"] == (
        "pre_activation_readiness_seed"
    )
    assert route["latest_metrics"] == {
        "pressure_status": "available",
        "pressure_age_seconds": 1.5,
    }
