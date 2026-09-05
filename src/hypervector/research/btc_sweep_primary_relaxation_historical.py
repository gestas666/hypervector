"""Chronological historical orchestration for the frozen BTC replay."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.btc_sweep_primary_relaxation_experiment import (
    BtcSweepHistoricalCell,
    BtcSweepHistoricalExperimentResult,
    build_historical_experiment_report,
)
from hypervector.research.btc_sweep_primary_relaxation_replay import (
    evaluate_btc_sweep_primary_relaxation,
)


_PARTITION_NAMES = ("development", "validation", "pseudo_holdout")
_SCENARIOS = {"nominal": 2.0, "stress": 5.0}
_WARMUP = pd.Timedelta(hours=55)
_MINUTE = pd.Timedelta(minutes=1)


@dataclass(frozen=True)
class BtcSweepHistoricalPartition:
    """One half-open chronological signal-entry partition."""

    name: str
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp

    def __post_init__(self) -> None:
        """Reject unsupported names or invalid chronological boundaries."""
        if self.name not in _PARTITION_NAMES:
            raise ValueError("unknown BTC sweep-relaxation partition")
        start = pd.Timestamp(self.start_utc)
        end = pd.Timestamp(self.end_utc)
        if start.tz is None or end.tz is None:
            raise ValueError("BTC sweep-relaxation partitions must be timezone-aware")
        if start >= end:
            raise ValueError("BTC sweep-relaxation partition start must precede end")
        if start != start.floor("h") or end != end.floor("h"):
            raise ValueError("BTC sweep-relaxation partitions must be hour-aligned")


def frozen_btc_sweep_historical_partitions() -> tuple[BtcSweepHistoricalPartition, ...]:
    """Return the exact chronological bounds frozen before economics were opened."""
    return (
        BtcSweepHistoricalPartition(
            "development",
            pd.Timestamp("2025-07-28T00:00:00Z"),
            pd.Timestamp("2026-01-28T00:00:00Z"),
        ),
        BtcSweepHistoricalPartition(
            "validation",
            pd.Timestamp("2026-01-28T00:00:00Z"),
            pd.Timestamp("2026-04-28T00:00:00Z"),
        ),
        BtcSweepHistoricalPartition(
            "pseudo_holdout",
            pd.Timestamp("2026-04-28T00:00:00Z"),
            pd.Timestamp("2026-07-28T00:00:00Z"),
        ),
    )


def run_btc_sweep_primary_relaxation_historical(
    minute_bars: pd.DataFrame,
    partitions: tuple[BtcSweepHistoricalPartition, ...] | None = None,
) -> BtcSweepHistoricalExperimentResult:
    """Run the two frozen friction scenarios without execution authority."""
    selected = _validated_partitions(
        partitions or frozen_btc_sweep_historical_partitions()
    )
    _validate_source_coverage(minute_bars, selected)
    cells: list[BtcSweepHistoricalCell] = []
    for partition in selected:
        segment = _partition_bars(minute_bars, partition)
        duration = (partition.end_utc - partition.start_utc).total_seconds() / 86_400.0
        for scenario, slippage in _SCENARIOS.items():
            replay = evaluate_btc_sweep_primary_relaxation(
                segment,
                slippage,
                entry_start_utc=partition.start_utc,
                entry_end_utc=partition.end_utc,
            )
            cells.append(
                BtcSweepHistoricalCell(partition.name, scenario, duration, replay)
            )
    return build_historical_experiment_report(cells)


def _validated_partitions(
    partitions: tuple[BtcSweepHistoricalPartition, ...],
) -> tuple[BtcSweepHistoricalPartition, ...]:
    if tuple(partition.name for partition in partitions) != _PARTITION_NAMES:
        raise ValueError("BTC sweep-relaxation partition order or identity drifted")
    for prior, current in zip(partitions, partitions[1:]):
        if prior.end_utc != current.start_utc:
            raise ValueError("BTC sweep-relaxation partitions must be contiguous")
    return partitions


def _validate_source_coverage(
    bars: pd.DataFrame,
    partitions: tuple[BtcSweepHistoricalPartition, ...],
) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("BTC sweep-relaxation source requires an aware DatetimeIndex")
    if bars.empty:
        raise ValueError("BTC sweep-relaxation source is empty")
    expected_last = partitions[-1].end_utc - _MINUTE
    if bars.index.min() > partitions[0].start_utc or bars.index.max() < expected_last:
        raise ValueError("BTC sweep-relaxation source does not cover frozen partitions")


def _partition_bars(
    bars: pd.DataFrame,
    partition: BtcSweepHistoricalPartition,
) -> pd.DataFrame:
    lower = max(bars.index.min(), partition.start_utc - _WARMUP)
    selected = bars.loc[(bars.index >= lower) & (bars.index < partition.end_utc)].copy()
    if selected.empty:
        raise ValueError(f"BTC sweep-relaxation partition is empty: {partition.name}")
    return selected
