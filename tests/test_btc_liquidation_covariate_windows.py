"""Outcome-blind BTC liquidation covariate-window planning tests."""

from __future__ import annotations


def test_plan_merges_only_within_partitions_and_excludes_crossings() -> None:
    """Overlapping requests merge without leaking across frozen boundaries."""
    from hypervector.research.btc_liquidation_covariate_windows import (
        EligibleEpisode,
        FrozenPartition,
        build_covariate_window_plan,
    )

    partitions = (
        FrozenPartition("development", 0, 100_000),
        FrozenPartition("validation", 100_000, 200_000),
    )
    episodes = (
        EligibleEpisode("a", 100),
        EligibleEpisode("b", 150),
        EligibleEpisode("crossing", 99_950),
        EligibleEpisode("c", 100_020),
        EligibleEpisode("unassigned", 300_000),
    )

    plan = build_covariate_window_plan(
        episodes,
        partitions,
        decision_delay_ms=10,
        pre_decision_ms=20,
        outcome_horizon_ms=100,
    )

    assert [
        (row.partition, row.start_ms, row.end_ms, row.episode_ids)
        for row in plan.windows
    ] == [
        ("development", 90, 260, ("a", "b")),
        ("validation", 100_010, 100_130, ("c",)),
    ]
    assert plan.included_episode_ids == ("a", "b", "c")
    assert plan.boundary_excluded_episode_ids == ("crossing",)
    assert plan.unassigned_episode_ids == ("unassigned",)
    assert plan.requested_duration_ms == 360
    assert plan.merged_duration_ms == 290


def test_merged_windows_are_chronological_not_name_sorted() -> None:
    """Partition labels cannot reorder acquisition time."""
    from hypervector.research.btc_liquidation_covariate_windows import (
        EligibleEpisode,
        FrozenPartition,
        build_covariate_window_plan,
    )

    partitions = (
        FrozenPartition("z_early", 0, 1_000),
        FrozenPartition("a_late", 1_000, 2_000),
    )
    episodes = (EligibleEpisode("early", 100), EligibleEpisode("late", 1_100))

    plan = build_covariate_window_plan(
        episodes,
        partitions,
        decision_delay_ms=0,
        pre_decision_ms=0,
        outcome_horizon_ms=10,
    )

    assert [row.partition for row in plan.windows] == ["z_early", "a_late"]


def test_plan_rejects_duplicate_episode_identity() -> None:
    """One treatment cannot consume acquisition duration twice."""
    import pytest

    from hypervector.research.btc_liquidation_covariate_windows import (
        EligibleEpisode,
        FrozenPartition,
        build_covariate_window_plan,
    )

    episodes = (EligibleEpisode("same", 100), EligibleEpisode("same", 200))

    with pytest.raises(ValueError, match="duplicate eligible episode_id"):
        build_covariate_window_plan(
            episodes,
            (FrozenPartition("development", 0, 1_000),),
            decision_delay_ms=0,
            pre_decision_ms=0,
            outcome_horizon_ms=10,
        )


def test_plan_rejects_overlapping_frozen_partitions() -> None:
    """Ambiguous partition membership must not depend on tuple order."""
    import pytest

    from hypervector.research.btc_liquidation_covariate_windows import (
        EligibleEpisode,
        FrozenPartition,
        build_covariate_window_plan,
    )

    partitions = (
        FrozenPartition("first", 0, 1_000),
        FrozenPartition("second", 900, 2_000),
    )

    with pytest.raises(ValueError, match="partitions overlap"):
        build_covariate_window_plan(
            (EligibleEpisode("event", 950),),
            partitions,
            decision_delay_ms=0,
            pre_decision_ms=0,
            outcome_horizon_ms=10,
        )


def test_hourly_acquisition_windows_cover_union_once() -> None:
    """Vendor-hour expansion must floor, ceil, and deduplicate plan coverage."""
    from hypervector.research.btc_liquidation_covariate_windows import (
        CovariateWindowPlan,
        MergedCovariateWindow,
        hourly_acquisition_windows,
    )

    plan = CovariateWindowPlan(
        windows=(
            MergedCovariateWindow("development", 90, 260, ("a", "b")),
            MergedCovariateWindow("validation", 100_010, 100_130, ("c",)),
        ),
        included_episode_ids=("a", "b", "c"),
        boundary_excluded_episode_ids=(),
        unassigned_episode_ids=(),
        requested_duration_ms=360,
        merged_duration_ms=290,
    )

    windows = hourly_acquisition_windows(plan, hour_ms=100)

    assert [(row.start_ms, row.end_ms) for row in windows] == [
        (0, 100),
        (100, 200),
        (200, 300),
        (100_000, 100_100),
        (100_100, 100_200),
    ]


def test_hourly_acquisition_windows_reject_nonpositive_bucket() -> None:
    """A malformed vendor cadence must fail before acquisition planning."""
    import pytest

    from hypervector.research.btc_liquidation_covariate_windows import (
        CovariateWindowPlan,
        hourly_acquisition_windows,
    )

    plan = CovariateWindowPlan((), (), (), (), 0, 0)

    with pytest.raises(ValueError, match="hour_ms must be positive"):
        hourly_acquisition_windows(plan, hour_ms=0)
