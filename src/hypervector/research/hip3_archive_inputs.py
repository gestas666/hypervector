"""Causal signal-source and chronology contracts for HIP-3 archive replay."""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite
from typing import Literal

import pandas as pd

from hypervector.hip3_pressure_contract import (
    ARCHIVE_PARITY_MAXIMUM_PRESSURE_AGE_MS,
    MINIMUM_PRESSURE_SNAPSHOTS,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)
from hypervector.research.hip3_swing_signals import (
    build_gap_aware_swing_ha_signals,
)
from hypervector.research.mu_hip3_candidate import MuChronologicalWindows
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

ArchiveSignalConfig = SwingHaSignalConfig | Hip3BreakoutPressureConfig
ArchiveSignalBuilder = Callable[[pd.DataFrame, ArchiveSignalConfig, str], pd.DataFrame]
ArchivePartitionName = Literal["development", "validation", "holdout"]
MAXIMUM_HOLD_SECONDS = 86_400


def build_archive_swing_signals(
    bars: pd.DataFrame, config: ArchiveSignalConfig, timeframe: str
) -> pd.DataFrame:
    """Build Swing/HA signals from the frozen public-trade OHLC source."""
    if not isinstance(config, SwingHaSignalConfig):
        raise TypeError("swing family requires SwingHaSignalConfig")
    return build_gap_aware_swing_ha_signals(
        signal_source_bars(bars), config, timeframe=timeframe
    )


def build_archive_breakout_signals(
    bars: pd.DataFrame, config: ArchiveSignalConfig, timeframe: str
) -> pd.DataFrame:
    """Build breakout signals after suppressing stale pre-close L2 pressure."""
    if not isinstance(config, Hip3BreakoutPressureConfig):
        raise TypeError("breakout family requires Hip3BreakoutPressureConfig")
    return build_breakout_pressure_signals(
        fresh_pressure_bars(signal_source_bars(bars)),
        config,
        timeframe=timeframe,
    )


def archive_family_builder(family: str) -> ArchiveSignalBuilder:
    """Return the causal builder for one supported archive family."""
    if family == "swing_ha":
        return build_archive_swing_signals
    if family == "breakout_pressure":
        return build_archive_breakout_signals
    raise ValueError(f"unsupported HIP-3 archive family: {family}")


def fresh_pressure_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Suppress pre-close archive pressure when its L2 boundary is stale."""
    age = pd.to_numeric(bars["end_boundary_age_ms"], errors="raise")
    snapshots = pd.to_numeric(bars["source_snapshot_count"], errors="raise")
    invalid = (
        not age.map(isfinite).all()
        or age.lt(0).any()
        or snapshots.lt(0).any()
        or not snapshots.mod(1).eq(0).all()
    )
    if invalid:
        raise ValueError("HIP-3 archive decision L2 freshness fields are invalid")
    output = bars.copy()
    fresh = age.le(ARCHIVE_PARITY_MAXIMUM_PRESSURE_AGE_MS) & snapshots.ge(
        MINIMUM_PRESSURE_SNAPSHOTS
    )
    output.loc[~fresh, "decision_imbalance_10"] = 0.0
    return output


def signal_source_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Freeze signals to venue trade OHLC while retaining L2 pressure fields."""
    columns = {
        "open": "signal_open",
        "high": "signal_high",
        "low": "signal_low",
        "close": "signal_close",
        "gap_before_bars": "signal_gap_before_bars",
    }
    contract = {
        *columns.values(),
        "signal_ohlc_source",
        "signal_ohlc_synthetic_no_trade",
    }
    present = contract.intersection(bars.columns)
    if not present:
        raise ValueError(
            "HIP-3 archive candidate requires the frozen public-trade OHLC source"
        )
    if present != contract:
        raise ValueError("HIP-3 signal OHLC source columns are incomplete")
    sources = set(bars["signal_ohlc_source"].astype(str))
    if sources != {"0xarchive_public_trade_ohlc_v1"}:
        raise ValueError("HIP-3 signal OHLC source identity is invalid")
    output = bars.copy()
    for target, source in columns.items():
        output[target] = bars[source]
    return output


def validate_archive_bars(bars: pd.DataFrame) -> None:
    """Require causal quotes, pressure, funding, and ordered UTC bars."""
    required = {
        "open",
        "high",
        "low",
        "close",
        "entry_bid",
        "entry_ask",
        "decision_bid",
        "decision_ask",
        "decision_imbalance_10",
        "first_boundary_delay_ms",
        "end_boundary_age_ms",
        "maximum_snapshot_interval_ms",
        "source_snapshot_count",
        "gap_before_bars",
        "funding_rate",
    }
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"HIP-3 archive bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("HIP-3 archive bars require timezone-aware timestamps")
    invalid_index = (
        bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique
    )
    if invalid_index:
        raise ValueError("HIP-3 archive bars require ordered unique timestamps")


def validate_development_only_partitions(
    names: tuple[ArchivePartitionName, ...],
) -> None:
    """Prevent the candidate search API from opening out-of-sample data."""
    if names != ("development",):
        raise ValueError("use the frozen-track API for out-of-sample partitions")


def partition_evaluation_end(
    windows: MuChronologicalWindows, partition: ArchivePartitionName
) -> pd.Timestamp:
    """Return the exclusive causal boundary for one named partition."""
    return {
        "development": windows.development_end_utc,
        "validation": windows.validation_end_utc,
        "holdout": windows.holdout_end_utc,
    }[partition]


def canonical_archive_windows(
    archive_start_utc: pd.Timestamp,
    archive_end_utc: pd.Timestamp,
) -> MuChronologicalWindows:
    """Return one shared 60/20/20 wall-clock split aligned to 15m bars."""
    start = pd.Timestamp(archive_start_utc).ceil("15min")
    end = pd.Timestamp(archive_end_utc).floor("15min")
    slots = int((end - start) / pd.Timedelta(minutes=15))
    development_slots = int(slots * 0.60)
    validation_slots = int(slots * 0.80)
    if development_slots < 6 or validation_slots - development_slots < 2:
        raise ValueError("HIP-3 archive is too short for shared 60/20/20 windows")
    development_end = start + development_slots * pd.Timedelta(minutes=15)
    folds = tuple(
        (
            start + (development_slots * fold // 3) * pd.Timedelta(minutes=15),
            start + (development_slots * (fold + 1) // 3) * pd.Timedelta(minutes=15),
        )
        for fold in range(3)
    )
    return MuChronologicalWindows(
        start,
        development_end,
        start + validation_slots * pd.Timedelta(minutes=15),
        end,
        folds,
    )


def validate_archive_windows(
    bars: pd.DataFrame, windows: MuChronologicalWindows, timeframe: str
) -> None:
    """Require ordered windows wholly contained by available chronology."""
    boundaries = (
        windows.development_start_utc,
        windows.development_end_utc,
        windows.validation_end_utc,
        windows.holdout_end_utc,
    )
    if tuple(sorted(boundaries)) != boundaries or len(set(boundaries)) != 4:
        raise ValueError("HIP-3 archive windows must be ordered and non-overlapping")
    minutes = 5 if timeframe == "5m" else 15
    final_close = bars.index[-1] + pd.Timedelta(minutes=minutes)
    if boundaries[0] < bars.index[0] or boundaries[-1] > final_close:
        raise ValueError("HIP-3 archive windows exceed available bar chronology")


def validate_archive_cadence(
    bars: pd.DataFrame, timeframe: str, maximum_hold_bars: int
) -> None:
    """Reconcile declared gaps, quote timing, and the 24-hour ceiling."""
    minutes = 5 if timeframe == "5m" else 15
    expected_hold = MAXIMUM_HOLD_SECONDS // (minutes * 60)
    if maximum_hold_bars != expected_hold:
        raise ValueError(
            f"HIP-3 {timeframe} maximum_hold_bars must equal {expected_hold}"
        )
    elapsed = bars.index.to_series().diff().dt.total_seconds().iloc[1:]
    gaps = bars["gap_before_bars"].astype(int).iloc[1:]
    expected = (gaps + 1) * minutes * 60
    if not elapsed.eq(expected).all():
        raise ValueError(f"HIP-3 archive bars violate declared {timeframe} cadence")
    _validate_quote_timing(bars, minutes)


def _validate_quote_timing(bars: pd.DataFrame, minutes: int) -> None:
    maximum_ms = float(minutes * 60_000)
    bounds = {
        "first_boundary_delay_ms": False,
        "end_boundary_age_ms": True,
        "maximum_snapshot_interval_ms": True,
    }
    for column, inclusive in bounds.items():
        values = pd.to_numeric(bars[column], errors="raise").astype(float)
        valid_upper = values.le(maximum_ms) if inclusive else values.lt(maximum_ms)
        invalid = (
            not values.map(isfinite).all()
            or values.lt(0.0).any()
            or not valid_upper.all()
        )
        if invalid:
            raise ValueError(
                f"HIP-3 {column} must be finite and within the {minutes}m bar"
            )
