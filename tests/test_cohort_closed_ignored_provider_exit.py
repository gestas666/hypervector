"""Durable ignored provider-exit evidence for closed live lifecycles."""

from dataclasses import dataclass

import pytest

from hypervector.research.cohort_ignored_provider_exit import (
    build_closed_ignored_provider_exit_outcome,
    build_provider_exit_policy_index,
)


@dataclass(frozen=True)
class _Candle:
    timestamp_ms: int
    high: float
    low: float
    close: float


def test_closed_outcome_compares_signal_path_with_actual_after_cost_exit() -> None:
    """The real close remains authoritative while signal-reference costs stay unknown."""
    outcome = build_closed_ignored_provider_exit_outcome(
        (_evaluation(180_000, 99.0, ("long",)),),
        {
            240_000: _Candle(240_000, 100.0, 98.8, 99.8),
        },
        side="long",
        entry={"venue_timestamp_ms": 100_000, "price": 100.0},
        exit_leg={"venue_timestamp_ms": 300_000, "price": 100.5},
        provider_recipe_exit_policy="ignore",
        actual_economics={
            "net_pnl_usd": 0.08,
            "fees_usd": 0.02,
            "funding_usd": -0.01,
            "exit_reason": "maximum_hold_seconds",
            "exit_controller_strategy_id": "cohort_maximum_hold",
        },
    )

    assert outcome["status"] == "observed"
    assert outcome["first_signal"]["reference_price"] == 99.0
    assert outcome["actual_exit"]["price"] == 100.5
    assert outcome["actual_exit"]["net_pnl_usd"] == 0.08
    assert outcome["gross_continuation_from_signal_bps"] == pytest.approx(
        (100.5 / 99.0 - 1.0) * 10_000.0
    )
    assert outcome["counterfactual_signal_exit_net_pnl_usd"] is None
    assert outcome["contract"]["execution_authority"] == "none"


def test_policy_index_recovers_default_ignore_and_rejects_mutation() -> None:
    """A bound lifecycle policy is immutable even across repeated transitions."""
    assets = {
        "BTC": [
            _transition(1, 11, {}),
            _transition(2, 11, {"provider_recipe_exit_policy": "ignore"}),
        ]
    }

    assert build_provider_exit_policy_index(assets) == {("BTC", 11): "ignore"}

    assets["BTC"].append(_transition(3, 11, {"provider_recipe_exit_policy": "honor"}))
    with pytest.raises(ValueError, match="changed provider recipe exit policy"):
        build_provider_exit_policy_index(assets)


def _evaluation(
    decision_time_ms: int,
    reference_price: float,
    exit_sides: tuple[str, ...],
) -> dict[str, object]:
    return {
        "decision_time_ms": decision_time_ms,
        "reference_price": reference_price,
        "decision_action": "close_long",
        "exit_sides": list(exit_sides),
        "exit_reason": "provider_flip",
        "readiness": {"conditions_met": 2, "conditions_required": 4},
    }


def _transition(
    sequence: int,
    entry_oid: int,
    policy: dict[str, object],
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "event_type": "state_transition",
        "payload": {
            "entry_oid": entry_oid,
            "execution_plan": {
                "strategy_id": "provider",
                **policy,
            },
        },
    }
