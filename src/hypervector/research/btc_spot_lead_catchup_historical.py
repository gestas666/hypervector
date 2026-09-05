"""Chronological orchestration for the BTC spot-lead catch-up replay."""

from __future__ import annotations

import pandas as pd

from hypervector.research.btc_spot_lead_catchup_experiment import (
    BtcSpotLeadCatchupCell,
    BtcSpotLeadCatchupExperimentResult,
    build_btc_spot_lead_catchup_report,
)
from hypervector.research.btc_spot_lead_catchup_replay import (
    evaluate_btc_spot_lead_catchup,
)
from hypervector.research.btc_sweep_primary_relaxation_historical import (
    BtcSweepHistoricalPartition,
    frozen_btc_sweep_historical_partitions,
)


BtcSpotLeadCatchupPartition = BtcSweepHistoricalPartition
_PARTITION_NAMES = ("development", "validation", "pseudo_holdout")
_SCENARIOS = {
    "nominal": (2.0, 0),
    "stress": (5.0, 0),
    "one_minute_entry_delay": (2.0, 1),
}
_WARMUP = pd.Timedelta(hours=55)
_MINUTE = pd.Timedelta(minutes=1)


def frozen_btc_spot_lead_catchup_partitions() -> tuple[
    BtcSpotLeadCatchupPartition,
    ...,
]:
    """Return the exact preregistered chronological partitions."""
    return frozen_btc_sweep_historical_partitions()


def run_btc_spot_lead_catchup_historical(
    perpetual_bars: pd.DataFrame,
    spot_bars: pd.DataFrame,
    partitions: tuple[BtcSpotLeadCatchupPartition, ...] | None = None,
) -> BtcSpotLeadCatchupExperimentResult:
    """Run all cross-venue partitions, arms, and scenarios without aborts."""
    selected = _validated_partitions(
        partitions or frozen_btc_spot_lead_catchup_partitions()
    )
    _validate_source_coverage(perpetual_bars, selected, "perpetual")
    _validate_source_coverage(spot_bars, selected, "spot")
    cells: list[BtcSpotLeadCatchupCell] = []
    for partition in selected:
        perpetual = _partition_bars(perpetual_bars, partition)
        spot = _partition_bars(spot_bars, partition)
        days = (partition.end_utc - partition.start_utc).total_seconds() / 86_400.0
        cells.extend(_partition_cells(perpetual, spot, partition, days))
    return build_btc_spot_lead_catchup_report(cells)


def _partition_cells(
    perpetual: pd.DataFrame,
    spot: pd.DataFrame,
    partition: BtcSpotLeadCatchupPartition,
    days: float,
) -> list[BtcSpotLeadCatchupCell]:
    cells: list[BtcSpotLeadCatchupCell] = []
    for scenario, (slippage, delay) in _SCENARIOS.items():
        replay = evaluate_btc_spot_lead_catchup(
            perpetual,
            spot,
            slippage,
            entry_delay_minutes=delay,
            entry_start_utc=partition.start_utc,
            entry_end_utc=partition.end_utc,
        )
        cells.append(BtcSpotLeadCatchupCell(partition.name, scenario, days, replay))
    return cells


def _validated_partitions(
    partitions: tuple[BtcSpotLeadCatchupPartition, ...],
) -> tuple[BtcSpotLeadCatchupPartition, ...]:
    if tuple(partition.name for partition in partitions) != _PARTITION_NAMES:
        raise ValueError("BTC spot-lead partition identity drifted")
    for prior, current in zip(partitions, partitions[1:]):
        if prior.end_utc != current.start_utc:
            raise ValueError("BTC spot-lead partitions must be contiguous")
    return partitions


def _validate_source_coverage(
    bars: pd.DataFrame,
    partitions: tuple[BtcSpotLeadCatchupPartition, ...],
    label: str,
) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError(f"BTC spot-lead {label} source requires an aware index")
    expected_last = partitions[-1].end_utc - _MINUTE
    if bars.empty or bars.index.min() > partitions[0].start_utc:
        raise ValueError(f"BTC spot-lead {label} source start is incomplete")
    if bars.index.max() < expected_last:
        raise ValueError(f"BTC spot-lead {label} source end is incomplete")


def _partition_bars(
    bars: pd.DataFrame,
    partition: BtcSpotLeadCatchupPartition,
) -> pd.DataFrame:
    lower = max(bars.index.min(), partition.start_utc - _WARMUP)
    selected = bars.loc[(bars.index >= lower) & (bars.index < partition.end_utc)].copy()
    if selected.empty:
        raise ValueError(f"BTC spot-lead partition is empty: {partition.name}")
    return selected
