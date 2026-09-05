from __future__ import annotations

import importlib

import pandas as pd

from btc_trend_pullback_fixtures import partitioned_market


def test_historical_runner_publishes_all_partition_scenario_arms() -> None:
    """Losing or sparse cells must not suppress registered output."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_historical"
    )
    bounds = pd.date_range("2025-01-01", periods=4, freq="72h", tz="UTC")
    partitions = tuple(
        module.BtcTrendPullbackPartition(name, bounds[index], bounds[index + 1])
        for index, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    result = module.run_btc_trend_pullback_historical(partitioned_market(), partitions)
    rows = result.report["summary_rows"]
    identities = {(row["partition"], row["scenario"], row["arm"]) for row in rows}
    assert len(identities) == 18
    assert result.report["authority"]["execution_authority"] == "none"
    assert result.report["acceptance"]["live_promotion_authorized"] is False


def test_historical_runner_publishes_registered_shared_route_cases() -> None:
    """Long, current-V58, and exact V51 cases retain every partition and cost."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_historical"
    )
    competition = importlib.import_module(
        "hypervector.research.btc_trend_pullback_route_competition"
    )
    bounds = pd.date_range("2025-01-01", periods=4, freq="72h", tz="UTC")
    partitions = tuple(
        module.BtcTrendPullbackPartition(name, bounds[index], bounds[index + 1])
        for index, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    hulk_events = tuple(
        event
        for index in range(3)
        for event in (
            competition.BtcRouteEvent.structural(
                "hulk_expansion_short_robust_v3",
                20,
                bounds[index] + pd.Timedelta(hours=10),
                130.0,
            ),
            competition.BtcRouteEvent.structural(
                "hulk_expansion_short_tuned_v2",
                19,
                bounds[index] + pd.Timedelta(hours=20),
                130.0,
            ),
        )
    )
    result = module.run_btc_trend_pullback_historical(
        partitioned_market(),
        partitions,
        hulk_events=hulk_events,
        hulk_source_identity={"status": "exact_test_fixture"},
    )
    route = result.report["route_competition"]
    assert route["status"] == "complete"
    assert len(route["comparison_rows"]) == 12
    assert len(route["v51_baseline_rows"]) == 6
    assert route["execution_authority"] == "none"
