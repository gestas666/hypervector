"""Chronological orchestration for the frozen BTC IBIT creation experiment."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.btc_ibit_creation_experiment import (
    BtcIbitCreationCell,
    BtcIbitCreationExperimentResult,
    build_btc_ibit_creation_report,
)
from hypervector.research.btc_ibit_creation_replay import (
    evaluate_btc_ibit_creation_long,
)


_PARTITION_NAMES = ("development", "validation", "pseudo_holdout")
_SCENARIOS = {
    "nominal": (2.0, 0),
    "stress": (5.0, 0),
    "publication_delay_24h": (2.0, 1_440),
}
_WARMUP = pd.Timedelta(hours=55)
_MINUTE = pd.Timedelta(minutes=1)


@dataclass(frozen=True)
class BtcIbitCreationPartition:
    """One half-open chronological issuer-signal entry partition."""

    name: str
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp

    def __post_init__(self) -> None:
        """Reject unsupported identities or ambiguous time boundaries."""
        if self.name not in _PARTITION_NAMES:
            raise ValueError("unknown BTC IBIT creation partition")
        start = pd.Timestamp(self.start_utc)
        end = pd.Timestamp(self.end_utc)
        if start.tz is None or end.tz is None:
            raise ValueError("BTC IBIT creation partitions must be timezone-aware")
        if start >= end:
            raise ValueError("BTC IBIT creation partition start must precede end")
        if start != start.floor("h") or end != end.floor("h"):
            raise ValueError("BTC IBIT creation partitions must be hour-aligned")


def frozen_btc_ibit_creation_partitions() -> tuple[BtcIbitCreationPartition, ...]:
    """Return the exact three chronological preregistration windows."""
    return (
        BtcIbitCreationPartition(
            "development",
            pd.Timestamp("2025-07-28T00:00:00Z"),
            pd.Timestamp("2026-01-28T00:00:00Z"),
        ),
        BtcIbitCreationPartition(
            "validation",
            pd.Timestamp("2026-01-28T00:00:00Z"),
            pd.Timestamp("2026-04-28T00:00:00Z"),
        ),
        BtcIbitCreationPartition(
            "pseudo_holdout",
            pd.Timestamp("2026-04-28T00:00:00Z"),
            pd.Timestamp("2026-07-28T00:00:00Z"),
        ),
    )


def run_btc_ibit_creation_historical(
    minute_bars: pd.DataFrame,
    ibit_history: pd.DataFrame,
    partitions: tuple[BtcIbitCreationPartition, ...] | None = None,
) -> BtcIbitCreationExperimentResult:
    """Run all frozen partitions, arms, and scenarios without abort gates."""
    selected = _validated_partitions(
        partitions or frozen_btc_ibit_creation_partitions()
    )
    _validate_source_coverage(minute_bars, selected)
    cells: list[BtcIbitCreationCell] = []
    for partition in selected:
        segment = _partition_bars(minute_bars, partition)
        days = (partition.end_utc - partition.start_utc).total_seconds() / 86_400.0
        cells.extend(_partition_cells(segment, ibit_history, partition, days))
    return build_btc_ibit_creation_report(cells)


def _partition_cells(
    bars: pd.DataFrame,
    history: pd.DataFrame,
    partition: BtcIbitCreationPartition,
    days: float,
) -> list[BtcIbitCreationCell]:
    output: list[BtcIbitCreationCell] = []
    for scenario, (slippage, delay) in _SCENARIOS.items():
        replay = evaluate_btc_ibit_creation_long(
            bars,
            history,
            slippage,
            publication_delay_minutes=delay,
            entry_start_utc=partition.start_utc,
            entry_end_utc=partition.end_utc,
        )
        output.append(BtcIbitCreationCell(partition.name, scenario, days, replay))
    return output


def _validated_partitions(
    partitions: tuple[BtcIbitCreationPartition, ...],
) -> tuple[BtcIbitCreationPartition, ...]:
    if tuple(partition.name for partition in partitions) != _PARTITION_NAMES:
        raise ValueError("BTC IBIT creation partition order or identity drifted")
    for prior, current in zip(partitions, partitions[1:]):
        if prior.end_utc != current.start_utc:
            raise ValueError("BTC IBIT creation partitions must be contiguous")
    return partitions


def _validate_source_coverage(
    bars: pd.DataFrame,
    partitions: tuple[BtcIbitCreationPartition, ...],
) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("BTC IBIT creation source requires an aware index")
    if bars.empty or not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError(
            "BTC IBIT creation source must be nonempty, unique, and ordered"
        )
    if bars.index.min() > partitions[0].start_utc:
        raise ValueError("BTC IBIT creation source start is incomplete")
    expected_last = partitions[-1].end_utc - _MINUTE
    if bars.index.max() < expected_last:
        raise ValueError("BTC IBIT creation source end is incomplete")


def _partition_bars(
    bars: pd.DataFrame,
    partition: BtcIbitCreationPartition,
) -> pd.DataFrame:
    lower = max(bars.index.min(), partition.start_utc - _WARMUP)
    selected = bars.loc[(bars.index >= lower) & (bars.index < partition.end_utc)].copy()
    if selected.empty:
        raise ValueError(f"BTC IBIT creation partition is empty: {partition.name}")
    return selected
