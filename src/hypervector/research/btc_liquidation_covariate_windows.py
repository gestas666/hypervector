"""Outcome-blind covariate-window planning for BTC liquidation episodes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrozenPartition:
    """One half-open chronological experiment partition in epoch milliseconds."""

    name: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class EligibleEpisode:
    """Minimum treatment identity needed before any outcome acquisition."""

    episode_id: str
    end_ms: int


@dataclass(frozen=True)
class MergedCovariateWindow:
    """One half-open union window contained by a frozen partition."""

    partition: str
    start_ms: int
    end_ms: int
    episode_ids: tuple[str, ...]


@dataclass(frozen=True)
class CovariateWindowPlan:
    """Outcome-blind acquisition union and explicit episode exclusions."""

    windows: tuple[MergedCovariateWindow, ...]
    included_episode_ids: tuple[str, ...]
    boundary_excluded_episode_ids: tuple[str, ...]
    unassigned_episode_ids: tuple[str, ...]
    requested_duration_ms: int
    merged_duration_ms: int


@dataclass(frozen=True)
class HourlyAcquisitionWindow:
    """One half-open vendor acquisition bucket in epoch milliseconds."""

    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class _RawWindow:
    partition: str
    start_ms: int
    end_ms: int
    episode_id: str


def build_covariate_window_plan(
    episodes: tuple[EligibleEpisode, ...],
    partitions: tuple[FrozenPartition, ...],
    *,
    decision_delay_ms: int = 10_000,
    pre_decision_ms: int = 60_000,
    outcome_horizon_ms: int = 15 * 60_000,
) -> CovariateWindowPlan:
    """Build partition-contained unions without reading any market outcome."""
    _validate_episode_ids(episodes)
    _validate_partitions(partitions)
    raw: list[_RawWindow] = []
    included: list[str] = []
    boundary: list[str] = []
    unassigned: list[str] = []
    for episode in episodes:
        decision_ms = episode.end_ms + decision_delay_ms
        partition = _partition_at(partitions, decision_ms)
        if partition is None:
            unassigned.append(episode.episode_id)
            continue
        start_ms = decision_ms - pre_decision_ms
        end_ms = decision_ms + outcome_horizon_ms
        if start_ms < partition.start_ms or end_ms > partition.end_ms:
            boundary.append(episode.episode_id)
            continue
        raw.append(_RawWindow(partition.name, start_ms, end_ms, episode.episode_id))
        included.append(episode.episode_id)
    windows = _merge_windows(raw)
    return CovariateWindowPlan(
        windows,
        tuple(included),
        tuple(boundary),
        tuple(unassigned),
        sum(row.end_ms - row.start_ms for row in raw),
        sum(row.end_ms - row.start_ms for row in windows),
    )


def hourly_acquisition_windows(
    plan: CovariateWindowPlan,
    *,
    hour_ms: int = 60 * 60_000,
) -> tuple[HourlyAcquisitionWindow, ...]:
    """Expand the merged union into unique chronological vendor buckets."""
    if hour_ms <= 0:
        raise ValueError("hour_ms must be positive")
    starts = {
        bucket_start
        for window in plan.windows
        for bucket_start in range(
            window.start_ms // hour_ms * hour_ms,
            window.end_ms,
            hour_ms,
        )
    }
    return tuple(
        HourlyAcquisitionWindow(start_ms, start_ms + hour_ms)
        for start_ms in sorted(starts)
    )


def _validate_episode_ids(episodes: tuple[EligibleEpisode, ...]) -> None:
    episode_ids = [row.episode_id for row in episodes]
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("duplicate eligible episode_id")


def _validate_partitions(partitions: tuple[FrozenPartition, ...]) -> None:
    ordered = sorted(partitions, key=lambda row: (row.start_ms, row.end_ms))
    for prior, current in zip(ordered, ordered[1:]):
        if current.start_ms < prior.end_ms:
            raise ValueError("frozen experiment partitions overlap")


def _partition_at(
    partitions: tuple[FrozenPartition, ...],
    timestamp_ms: int,
) -> FrozenPartition | None:
    return next(
        (
            partition
            for partition in partitions
            if partition.start_ms <= timestamp_ms < partition.end_ms
        ),
        None,
    )


def _merge_windows(raw: list[_RawWindow]) -> tuple[MergedCovariateWindow, ...]:
    merged: list[MergedCovariateWindow] = []
    for row in sorted(
        raw,
        key=lambda item: (item.start_ms, item.end_ms, item.partition),
    ):
        if not merged or merged[-1].partition != row.partition:
            merged.append(
                MergedCovariateWindow(
                    row.partition, row.start_ms, row.end_ms, (row.episode_id,)
                )
            )
            continue
        prior = merged[-1]
        if row.start_ms > prior.end_ms:
            merged.append(
                MergedCovariateWindow(
                    row.partition, row.start_ms, row.end_ms, (row.episode_id,)
                )
            )
            continue
        merged[-1] = MergedCovariateWindow(
            prior.partition,
            prior.start_ms,
            max(prior.end_ms, row.end_ms),
            prior.episode_ids + (row.episode_id,),
        )
    return tuple(merged)
