"""Research priorities must follow the exact executable side contract."""

import pytest

from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)
from test_cohort_continuous_improvement import _checkpoint, _digest


@pytest.mark.parametrize("side", ["long", "short"])
def test_dual_source_one_side_execution_requests_attainable_evidence(side: str) -> None:
    """A dual signal source cannot demand an unconfigured live direction."""
    checkpoint = _checkpoint()
    generation = checkpoint["configuration_generation"]
    execution = generation["current_provider_execution_directions"]
    generation["current_provider_observation_directions"] = dict(execution)
    execution["range|SOL"] = [side]

    report = build_continuous_improvement_report(checkpoint, _digest())

    row = next(r for r in report["experiment_queue"] if r["route"] == "range|SOL")
    assert row["configured_directions"] == [side]
    assert row["next_experiment"] == "collect_side_specific_evidence"
    assert row["execution_enabled"] is True


def test_execution_direction_absent_from_source_is_an_evidence_error() -> None:
    """Inconsistent scope must fail instead of inventing signal support."""
    checkpoint = _checkpoint()
    generation = checkpoint["configuration_generation"]
    execution = generation["current_provider_execution_directions"]
    generation["current_provider_observation_directions"] = dict(execution)
    generation["current_provider_observation_directions"]["range|SOL"] = ["long"]

    with pytest.raises(ValueError, match="execution directions exceed observation"):
        build_continuous_improvement_report(checkpoint, _digest())
