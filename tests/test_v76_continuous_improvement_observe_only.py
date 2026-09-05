"""V76 research monitoring must retain observe-only route scope explicitly."""

from __future__ import annotations

from pathlib import Path

from hypervector.research.cohort_configuration_generation import (
    configuration_generation_evidence,
    load_configuration_expectation,
)
from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)
from test_cohort_continuous_improvement import (
    _checkpoint,
    _digest,
    _queue,
    _score,
)

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_validated_roster_candidate_v76.toml"
)
_OBSERVER_ROUTE = "research_pending_market_observer_bidirectional_15m_v1|ZEC"


def test_configuration_generation_separates_observation_from_execution() -> None:
    """Every visible route needs source-backed sides without acquiring authority."""
    expectation = load_configuration_expectation(_CONFIG)
    observed = {
        (provider, symbol): sides
        for provider, symbol, sides in expectation.provider_observation_directions
    }
    executable = {
        (provider, symbol): sides
        for provider, symbol, sides in expectation.provider_execution_directions
    }

    assert len(observed) == 9
    assert len(executable) == 5
    assert observed[
        ("research_pending_market_observer_bidirectional_15m_v1", "ZEC")
    ] == ("long", "short")
    assert (
        "research_pending_market_observer_bidirectional_15m_v1",
        "ZEC",
    ) not in executable
    evidence = configuration_generation_evidence(
        expectation.profile_fingerprint,
        expectation,
        {},
    )
    assert evidence["current_provider_observation_directions"][_OBSERVER_ROUTE] == [
        "long",
        "short",
    ]
    assert _OBSERVER_ROUTE not in evidence["current_provider_execution_directions"]
    assert evidence["execution_authority"] == "none"


def test_improvement_report_includes_observe_only_route_without_entry_authority() -> (
    None
):
    """The research queue must not erase a visible execution-disabled strategy."""
    checkpoint = _checkpoint()
    digest = _digest()
    generation = checkpoint["configuration_generation"]
    execution = generation["current_provider_execution_directions"]
    generation["current_provider_observation_directions"] = {
        **execution,
        _OBSERVER_ROUTE: ["long", "short"],
    }
    scorecards = checkpoint["audit"]["strategy_scorecard"]["by_provider_symbol"]
    scorecards[_OBSERVER_ROUTE] = _score(
        "tested_families_rejected_new_mechanism_required",
        {"long": {}, "short": {}},
    )
    digest["experiment_queue"].append(
        _queue(_OBSERVER_ROUTE, "new_mechanic_version_required", 6)
    )

    report = build_continuous_improvement_report(checkpoint, digest)

    observer = next(
        row for row in report["experiment_queue"] if row["route"] == _OBSERVER_ROUTE
    )
    assert observer["configured_directions"] == ["long", "short"]
    assert _OBSERVER_ROUTE not in execution
    assert report["proposal_contract"]["execution_authority"] == "none"


def test_observe_only_route_requests_forward_paths_not_live_execution() -> None:
    """Research work must be attainable without granting an observer authority."""
    checkpoint = _checkpoint()
    generation = checkpoint["configuration_generation"]
    execution = generation["current_provider_execution_directions"]
    generation["current_provider_observation_directions"] = dict(execution)
    execution.pop("range|SOL")

    report = build_continuous_improvement_report(checkpoint, _digest())

    sol = next(row for row in report["experiment_queue"] if row["route"] == "range|SOL")
    assert sol["execution_enabled"] is False
    assert sol["next_experiment"] == "collect_both_side_forward_paths"
    assert report["highest_value_next_investigation"]["experiment"] == (
        "collect_both_side_forward_paths"
    )
