"""Chronological orchestration for the BTC negative-funding breakout replay."""

from __future__ import annotations

import pandas as pd

from hypervector.research.btc_negative_funding_breakout_experiment import (
    BtcNegativeFundingBreakoutCell,
    BtcNegativeFundingBreakoutExperimentResult,
    build_btc_negative_funding_breakout_report,
)
from hypervector.research.btc_negative_funding_breakout_replay import (
    evaluate_btc_negative_funding_breakout,
)
from hypervector.research.btc_sweep_primary_relaxation_historical import (
    BtcSweepHistoricalPartition,
    frozen_btc_sweep_historical_partitions,
)


BtcNegativeFundingBreakoutPartition = BtcSweepHistoricalPartition
_PARTITION_NAMES = ("development", "validation", "pseudo_holdout")
_SCENARIOS = {
    "nominal": (2.0, 0),
    "stress": (5.0, 0),
    "one_minute_entry_delay": (2.0, 1),
}
_WARMUP = pd.Timedelta(hours=55)
_MINUTE = pd.Timedelta(minutes=1)


def frozen_btc_negative_funding_breakout_partitions() -> tuple[
    BtcNegativeFundingBreakoutPartition,
    ...,
]:
    """Return the exact preregistered chronological partitions."""
    return frozen_btc_sweep_historical_partitions()


def run_btc_negative_funding_breakout_historical(
    minute_bars: pd.DataFrame,
    hourly_funding: pd.Series,
    partitions: tuple[BtcNegativeFundingBreakoutPartition, ...] | None = None,
) -> BtcNegativeFundingBreakoutExperimentResult:
    """Run all partitions and scenarios without performance aborts."""
    selected = _validated_partitions(
        partitions or frozen_btc_negative_funding_breakout_partitions()
    )
    _validate_source_coverage(minute_bars, selected)
    cells: list[BtcNegativeFundingBreakoutCell] = []
    for partition in selected:
        segment = _partition_bars(minute_bars, partition)
        days = (partition.end_utc - partition.start_utc).total_seconds() / 86_400.0
        cells.extend(_partition_cells(segment, hourly_funding, partition, days))
    return build_btc_negative_funding_breakout_report(cells)


def _partition_cells(
    bars: pd.DataFrame,
    funding: pd.Series,
    partition: BtcNegativeFundingBreakoutPartition,
    days: float,
) -> list[BtcNegativeFundingBreakoutCell]:
    cells: list[BtcNegativeFundingBreakoutCell] = []
    for scenario, (slippage, delay) in _SCENARIOS.items():
        replay = evaluate_btc_negative_funding_breakout(
            bars,
            funding,
            slippage,
            entry_delay_minutes=delay,
            entry_start_utc=partition.start_utc,
            entry_end_utc=partition.end_utc,
        )
        cells.append(
            BtcNegativeFundingBreakoutCell(
                partition.name,
                scenario,
                days,
                replay,
            )
        )
    return cells


def _validated_partitions(
    partitions: tuple[BtcNegativeFundingBreakoutPartition, ...],
) -> tuple[BtcNegativeFundingBreakoutPartition, ...]:
    if tuple(partition.name for partition in partitions) != _PARTITION_NAMES:
        raise ValueError("BTC negative-funding partition identity drifted")
    for prior, current in zip(partitions, partitions[1:]):
        if prior.end_utc != current.start_utc:
            raise ValueError("BTC negative-funding partitions must be contiguous")
    return partitions


def _validate_source_coverage(
    bars: pd.DataFrame,
    partitions: tuple[BtcNegativeFundingBreakoutPartition, ...],
) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("BTC negative-funding source requires an aware index")
    expected_last = partitions[-1].end_utc - _MINUTE
    if bars.empty or bars.index.min() > partitions[0].start_utc:
        raise ValueError("BTC negative-funding source start is incomplete")
    if bars.index.max() < expected_last:
        raise ValueError("BTC negative-funding source end is incomplete")


def _partition_bars(
    bars: pd.DataFrame,
    partition: BtcNegativeFundingBreakoutPartition,
) -> pd.DataFrame:
    lower = max(bars.index.min(), partition.start_utc - _WARMUP)
    selected = bars.loc[(bars.index >= lower) & (bars.index < partition.end_utc)].copy()
    if selected.empty:
        raise ValueError(f"BTC negative-funding partition is empty: {partition.name}")
    return selected
