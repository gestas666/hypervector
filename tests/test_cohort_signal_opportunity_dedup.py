"""Portfolio-level deduplication tests for cohort signal outcomes."""

from __future__ import annotations

from copy import deepcopy

import pytest

from cohort_signal_outcomes_fixtures import (
    DECISION_MS,
    RUN_ID,
    STRATEGY,
    cohort_rows,
    payload,
)
from hypervector.research.cohort_signal_outcomes import (
    build_provider_forward_diagnostics,
)


def test_portfolio_opportunity_dedup_counts_shared_provider_path_once() -> None:
    """The same causal market path cannot become two portfolio opportunities."""
    outcomes = build_provider_forward_diagnostics(_two_provider_rows())

    dedup = outcomes["portfolio_opportunity_dedup"]
    assert isinstance(dedup, dict)
    assert dedup["provider_observations"] == 2
    assert dedup["unique_directional_paths"] == 1
    assert dedup["duplicate_provider_observations_removed"] == 1
    assert dedup["cross_provider_path_groups"] == 1
    horizon = dedup["horizons"]["5"]
    assert horizon["resolved"] == 1
    assert horizon["opportunity_capture"]["cost_clearing_close_count"] == 1
    assert dedup["provider_overlap"] == [
        {
            "group_count": 1,
            "providers": [
                {"blocker": "awaiting_breakout", "strategy_id": STRATEGY},
                {
                    "blocker": "awaiting_hourly_cross",
                    "strategy_id": "test_breakout_1m",
                },
            ],
        }
    ]


def test_portfolio_opportunity_dedup_attributes_unique_path_outcomes() -> None:
    """Unique path outcomes retain exact symbol, side, provider, and blocker."""
    outcomes = build_provider_forward_diagnostics(_two_provider_rows())

    dedup = outcomes["portfolio_opportunity_dedup"]
    assert isinstance(dedup, dict)
    attribution = dedup["by_attribution"]
    assert isinstance(attribution, list) and len(attribution) == 1
    _assert_attribution(attribution[0])


def _two_provider_rows() -> list[dict[str, object]]:
    rows = cohort_rows()
    evaluations = payload(rows[1])["evaluations"]
    assert isinstance(evaluations, list) and isinstance(evaluations[0], dict)
    first = evaluations[0]
    first.update({"eligible": False, "side": None, "decision_action": "hold"})
    readiness = first["readiness"]
    assert isinstance(readiness, dict)
    readiness["blockers"] = ["awaiting_breakout"]
    second = deepcopy(first)
    second["strategy_id"] = "test_breakout_1m"
    second_readiness = second["readiness"]
    assert isinstance(second_readiness, dict)
    second_readiness["blockers"] = ["awaiting_hourly_cross"]
    evaluations.append(second)
    return rows


def _assert_attribution(row: dict[str, object]) -> None:
    assert row["source_run_id"] == RUN_ID
    assert row["symbol"] == "BTC"
    assert row["side"] == "long"
    assert row["path_groups"] == 1
    assert row["decision_cadence"] == {
        "coverage_rate": 1.0,
        "decision_minutes": 1,
        "episode_count": 1,
        "maximum_episode_duration_minutes": 1,
        "maximum_interval_minutes": None,
        "median_episode_duration_minutes": 1.0,
        "median_interval_minutes": None,
        "minute_boundaries_in_span": 1,
        "single_minute_episodes": 1,
    }
    assert row["providers"] == [
        {"blocker": "awaiting_breakout", "strategy_id": STRATEGY},
        {
            "blocker": "awaiting_hourly_cross",
            "strategy_id": "test_breakout_1m",
        },
    ]
    _assert_path(row["horizons"]["5"])


def _assert_path(horizon: dict[str, object]) -> None:
    assert horizon["resolved"] == 1
    assert horizon["opportunity_capture"]["cost_clearing_close_count"] == 1
    assert horizon["independent_paths"] == [
        {
            "adverse_excursion_bps": pytest.approx(100.0),
            "decision_time_ms": DECISION_MS,
            "directional_close_return_bps": pytest.approx(500.0),
            "favorable_excursion_bps": pytest.approx(600.0),
            "latest_available_time_ms": DECISION_MS,
            "path_start_time_ms": DECISION_MS,
            "reference_price": 100.0,
            "source_run_id": RUN_ID,
        }
    ]
    assert horizon["episode_onsets"]["resolved"] == 1
    assert (
        horizon["episode_onsets"]["independent_paths"] == horizon["independent_paths"]
    )
