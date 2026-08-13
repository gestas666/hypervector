"""Prospective SOL Hulk exact-one-blocker observer contracts."""

import pytest

from hypervector.research.cohort_forward_experiments import (
    forward_experiment,
    source_authority_matches,
)

_CUTOFF_MS = 1_786_078_920_000


@pytest.mark.parametrize(
    ("name", "candidate", "blocker"),
    [
        (
            "v12-sol-hulk-expansion-trigger-fixed",
            "sol_hulk_expansion_trigger_relaxed_fixed60_bidirectional_v1",
            "expansion_trigger_not_present",
        ),
    ],
)
def test_sol_hulk_observers_are_frozen_after_discovery(
    name: str,
    candidate: str,
    blocker: str,
) -> None:
    """Both hypotheses must start prospectively and remain observe-only."""
    experiment = forward_experiment(name)

    assert experiment.candidate_strategy_id == candidate
    assert experiment.source_strategy_id == "hulk_expansion_bidirectional_tuned_v2"
    assert experiment.symbol == "SOL"
    assert experiment.blocker == blocker
    assert experiment.cutoff_time_ms == _CUTOFF_MS
    assert experiment.funding_start_time_ms == _CUTOFF_MS
    assert experiment.source_stop_policy == "structural_clamped_bps"
    assert experiment.source_stop_range_bps == (20.0, 75.0)
    assert experiment.stop_proxy_bps == 75.0
    assert experiment.target_proxy_bps is None
    assert experiment.opi_cohort == "all"
    assert experiment.notional_usd == 75.0
    assert experiment.source_authority == "observe_only"


@pytest.mark.parametrize(
    "name",
    [
        "v12-sol-hulk-expansion-trigger-fixed",
    ],
)
def test_sol_hulk_observer_accepts_v14_observe_only_source(name: str) -> None:
    """Research replay must bind to, but not promote, the v14 SOL provider."""
    experiment = forward_experiment(name)

    assert source_authority_matches(experiment, ("BTC",)) is True
    assert source_authority_matches(experiment, ("BTC", "SOL")) is False
