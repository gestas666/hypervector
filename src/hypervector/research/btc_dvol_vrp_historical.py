"""Chronological orchestration for the frozen BTC DVOL-VRP experiment."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.research.btc_dvol_vrp_experiment import (
    BtcDvolVrpCell,
    BtcDvolVrpExperimentResult,
    build_btc_dvol_vrp_report,
)
from hypervector.research.btc_dvol_vrp_features import (
    build_btc_dvol_vrp_features,
)
from hypervector.research.btc_dvol_vrp_replay import evaluate_btc_dvol_vrp_long


_PARTITION_NAMES = ("development", "validation", "pseudo_holdout")
_SCENARIOS = ("nominal", "stress", "delayed")
_WARMUP = pd.Timedelta(hours=2_881)
_MINUTE = pd.Timedelta(minutes=1)
_HOUR = pd.Timedelta(hours=1)


@dataclass(frozen=True)
class BtcDvolVrpPartition:
    """One half-open chronological DVOL-VRP entry partition."""

    name: str
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp

    def __post_init__(self) -> None:
        """Reject unsupported identities or ambiguous time boundaries."""
        if self.name not in _PARTITION_NAMES:
            raise ValueError("unknown BTC DVOL-VRP partition")
        start = pd.Timestamp(self.start_utc)
        end = pd.Timestamp(self.end_utc)
        if start.tz is None or end.tz is None:
            raise ValueError("BTC DVOL-VRP partitions must be timezone-aware")
        if start >= end:
            raise ValueError("BTC DVOL-VRP partition start must precede end")
        if start != start.floor("h") or end != end.floor("h"):
            raise ValueError("BTC DVOL-VRP partitions must be hour-aligned")


def frozen_btc_dvol_vrp_partitions() -> tuple[BtcDvolVrpPartition, ...]:
    """Return the exact three chronological preregistration windows."""
    return (
        BtcDvolVrpPartition(
            "development",
            pd.Timestamp("2025-07-28T00:00:00Z"),
            pd.Timestamp("2026-01-28T00:00:00Z"),
        ),
        BtcDvolVrpPartition(
            "validation",
            pd.Timestamp("2026-01-28T00:00:00Z"),
            pd.Timestamp("2026-04-28T00:00:00Z"),
        ),
        BtcDvolVrpPartition(
            "pseudo_holdout",
            pd.Timestamp("2026-04-28T00:00:00Z"),
            pd.Timestamp("2026-07-28T00:00:00Z"),
        ),
    )


def run_btc_dvol_vrp_historical(
    minute_bars: pd.DataFrame,
    dvol_hourly: pd.DataFrame,
    partitions: tuple[BtcDvolVrpPartition, ...] | None = None,
) -> BtcDvolVrpExperimentResult:
    """Run every frozen partition, arm, and scenario without abort gates."""
    selected = _validated_partitions(partitions or frozen_btc_dvol_vrp_partitions())
    _validate_market_coverage(minute_bars, selected)
    btc_hourly = _completed_hourly_btc(minute_bars)
    aligned_dvol = _aligned_dvol(dvol_hourly, btc_hourly)
    features = build_btc_dvol_vrp_features(btc_hourly, aligned_dvol)
    cells: list[BtcDvolVrpCell] = []
    for partition in selected:
        bars = _partition_bars(minute_bars, partition)
        feature_segment = _partition_features(features, bars, partition)
        cells.extend(_partition_cells(bars, feature_segment, partition))
    return build_btc_dvol_vrp_report(cells)


def _partition_cells(
    bars: pd.DataFrame,
    features: pd.DataFrame,
    partition: BtcDvolVrpPartition,
) -> list[BtcDvolVrpCell]:
    days = (partition.end_utc - partition.start_utc).total_seconds() / 86_400.0
    return [
        BtcDvolVrpCell(
            partition.name,
            scenario,
            days,
            evaluate_btc_dvol_vrp_long(
                bars,
                features,
                scenario,
                entry_start_utc=partition.start_utc,
                entry_end_utc=partition.end_utc,
            ),
        )
        for scenario in _SCENARIOS
    ]


def _validated_partitions(
    partitions: tuple[BtcDvolVrpPartition, ...],
) -> tuple[BtcDvolVrpPartition, ...]:
    if tuple(partition.name for partition in partitions) != _PARTITION_NAMES:
        raise ValueError("BTC DVOL-VRP partition order or identity drifted")
    for prior, current in zip(partitions, partitions[1:]):
        if prior.end_utc != current.start_utc:
            raise ValueError("BTC DVOL-VRP partitions must be contiguous")
    return partitions


def _validate_market_coverage(
    bars: pd.DataFrame,
    partitions: tuple[BtcDvolVrpPartition, ...],
) -> None:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("BTC DVOL-VRP source requires an aware index")
    if bars.empty or not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError("BTC DVOL-VRP source must be nonempty, unique, and ordered")
    cadence = bars.index.to_series().diff().dropna()
    if not cadence.eq(_MINUTE).all():
        raise ValueError("BTC DVOL-VRP source requires uninterrupted minute cadence")
    if bars.index.min() > partitions[0].start_utc:
        raise ValueError("BTC DVOL-VRP source start is incomplete")
    if bars.index.max() < partitions[-1].end_utc - _MINUTE:
        raise ValueError("BTC DVOL-VRP source end is incomplete")


def _completed_hourly_btc(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"BTC DVOL-VRP source lacks OHLC columns: {missing}")
    grouped = bars.resample("1h", label="left", closed="left")
    hourly = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    complete = grouped.size().eq(60)
    if not complete.all():
        raise ValueError("BTC DVOL-VRP source has incomplete hourly BTC bars")
    return hourly.reset_index(names="timestamp")


def _aligned_dvol(dvol: pd.DataFrame, btc: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" not in dvol:
        raise ValueError("BTC DVOL-VRP DVOL coverage lacks timestamp")
    candidate = dvol.copy()
    candidate["timestamp"] = pd.to_datetime(candidate["timestamp"], utc=True)
    expected = pd.DatetimeIndex(btc["timestamp"])
    observed = pd.DatetimeIndex(candidate["timestamp"])
    if observed.has_duplicates or not observed.is_monotonic_increasing:
        raise ValueError("BTC DVOL-VRP DVOL coverage is duplicate or unordered")
    selected = candidate.loc[candidate["timestamp"].isin(expected)].copy()
    selected_index = pd.DatetimeIndex(selected["timestamp"])
    allowed_extra = expected[-1] + _HOUR
    extras = observed.difference(expected)
    if not selected_index.equals(expected) or not extras.isin([allowed_extra]).all():
        raise ValueError("BTC DVOL-VRP DVOL coverage does not match BTC hours")
    return selected.reset_index(drop=True)


def _partition_bars(
    bars: pd.DataFrame,
    partition: BtcDvolVrpPartition,
) -> pd.DataFrame:
    lower = max(bars.index.min(), partition.start_utc - _WARMUP)
    selected = bars.loc[(bars.index >= lower) & (bars.index < partition.end_utc)].copy()
    if selected.empty:
        raise ValueError(f"BTC DVOL-VRP partition is empty: {partition.name}")
    return selected


def _partition_features(
    features: pd.DataFrame,
    bars: pd.DataFrame,
    partition: BtcDvolVrpPartition,
) -> pd.DataFrame:
    lower = bars.index.min().floor("h")
    selected = features.loc[
        (features["source_timestamp"] >= lower)
        & (features["decision_time"] < partition.end_utc)
    ].copy()
    if selected.empty:
        raise ValueError(f"BTC DVOL-VRP feature partition is empty: {partition.name}")
    return selected.reset_index(drop=True)
