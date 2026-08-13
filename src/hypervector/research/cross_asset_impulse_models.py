"""Typed contracts for report-only cross-asset impulse research."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal

import pandas as pd

DirectedPair = tuple[str, str]
ImpulseDirection = Literal["long", "short"]
ImpulseSignalVariant = Literal[
    "primary",
    "leader_only_ablation",
    "follower_only_momentum",
    "lagged_leader_placebo",
]
ImpulseAnchor = Literal["base", "delayed"]
ImpulseLabelStatus = Literal[
    "resolved",
    "technical_gap",
    "fold_boundary_purged",
    "right_censored",
]

_DEFAULT_START = pd.Timestamp("2025-07-28T00:00:00Z")
_DEFAULT_END = pd.Timestamp("2026-01-28T00:00:00Z")
_DEFAULT_FOLDS = (
    ("fold_1", _DEFAULT_START, pd.Timestamp("2025-09-28T00:00:00Z")),
    (
        "fold_2",
        pd.Timestamp("2025-09-28T00:00:00Z"),
        pd.Timestamp("2025-11-28T00:00:00Z"),
    ),
    ("fold_3", pd.Timestamp("2025-11-28T00:00:00Z"), _DEFAULT_END),
)


def declared_impulse_pairs() -> tuple[DirectedPair, ...]:
    """Return the frozen leader-to-follower hierarchy."""
    return (
        ("BTC", "ETH"),
        ("BTC", "SOL"),
        ("BTC", "HYPE"),
        ("ETH", "SOL"),
        ("ETH", "HYPE"),
    )


def declared_impulse_variants() -> tuple[ImpulseSignalVariant, ...]:
    """Return one selectable signal and three fixed non-selectable controls."""
    return (
        "primary",
        "leader_only_ablation",
        "follower_only_momentum",
        "lagged_leader_placebo",
    )


@dataclass(frozen=True)
class CrossAssetImpulseConfig:
    """Frozen timing, feature, label, and feasibility contract."""

    warmup_start: pd.Timestamp = field(
        default_factory=lambda: pd.Timestamp("2025-07-20T23:55:00Z")
    )
    development_start: pd.Timestamp = field(default_factory=lambda: _DEFAULT_START)
    development_end: pd.Timestamp = field(default_factory=lambda: _DEFAULT_END)
    impulse_return_minutes: int = 5
    lookback_minutes: int = 10_080
    minimum_valid_returns: int = 9_980
    leader_z_threshold: float = 2.5
    catchup_gap_threshold: float = 0.75
    cooldown_minutes: int = 30
    horizons_minutes: tuple[int, ...] = (5, 15, 30)
    fold_count: int = 3
    delayed_entry_minutes: int = 1
    placebo_lag_minutes: int = 1_440
    nominal_round_trip_cost_bps: float = 13.0
    stress_round_trip_cost_bps: float = 20.0
    minimum_events_per_fold: int = 30
    minimum_direction_events_per_fold: int = 10
    minimum_base_fold_mean_bps: float = 20.0
    minimum_base_median_fold_mean_bps: float = 26.0
    minimum_direction_mean_bps: float = 13.0
    minimum_delayed_fold_mean_bps: float = 13.0
    minimum_delayed_median_fold_mean_bps: float = 20.0
    minimum_events_per_day: float = 1.0
    maximum_p90_interarrival_minutes: float = 4_320.0
    report_only: bool = field(default=True, init=False)
    execution_authority: Literal["none"] = field(default="none", init=False)

    def __post_init__(self) -> None:
        """Reject incoherent research contracts before data is inspected."""
        _validate_window(self.warmup_start, self.development_start)
        _validate_window(self.development_start, self.development_end)
        _minimum_integer(self.impulse_return_minutes, 1, "impulse_return_minutes")
        _minimum_integer(self.lookback_minutes, 2, "lookback_minutes")
        if self.lookback_minutes < self.impulse_return_minutes:
            raise ValueError("lookback_minutes must cover impulse_return_minutes")
        _minimum_integer(self.minimum_valid_returns, 2, "minimum_valid_returns")
        if self.minimum_valid_returns > self.lookback_minutes:
            raise ValueError("minimum_valid_returns cannot exceed lookback_minutes")
        _positive(self.leader_z_threshold, "leader_z_threshold")
        _nonnegative(self.catchup_gap_threshold, "catchup_gap_threshold")
        _validate_horizons(self.horizons_minutes)
        if self.cooldown_minutes < max(self.horizons_minutes):
            raise ValueError("cooldown_minutes must cover the longest horizon")
        _minimum_integer(self.fold_count, 2, "fold_count")
        _minimum_integer(self.delayed_entry_minutes, 1, "delayed_entry_minutes")
        _minimum_integer(self.placebo_lag_minutes, 1, "placebo_lag_minutes")
        _positive(self.nominal_round_trip_cost_bps, "cost")
        _positive(self.stress_round_trip_cost_bps, "stress cost")
        if self.stress_round_trip_cost_bps < self.nominal_round_trip_cost_bps:
            raise ValueError("stress cost must not be below nominal cost")
        _validate_selection_thresholds(self)


def declared_impulse_folds(
    config: CrossAssetImpulseConfig,
) -> tuple[tuple[str, pd.Timestamp, pd.Timestamp], ...]:
    """Return exact production folds or deterministic fixture partitions."""
    if (
        config.development_start == _DEFAULT_START
        and config.development_end == _DEFAULT_END
        and config.fold_count == 3
    ):
        return _DEFAULT_FOLDS
    total = config.development_end.value - config.development_start.value
    boundaries = [
        config.development_start
        + pd.Timedelta(total * index // config.fold_count, unit="ns")
        for index in range(config.fold_count + 1)
    ]
    return tuple(
        (f"fold_{index}", start, end)
        for index, (start, end) in enumerate(
            zip(boundaries[:-1], boundaries[1:], strict=True), start=1
        )
    )


@dataclass(frozen=True)
class CrossAssetImpulseEvent:
    """One causal leader/follower event under a primary or control signal."""

    bar_open_at: str
    decision_time_utc: str
    entry_time_utc: str
    leader_symbol: str
    follower_symbol: str
    signal_variant: ImpulseSignalVariant
    direction: ImpulseDirection
    leader_zscore: float
    follower_zscore: float
    catchup_gap_z: float
    leader_valid_returns: int
    follower_valid_returns: int
    report_only: bool = field(default=True, init=False)
    execution_authority: Literal["none"] = field(default="none", init=False)


@dataclass(frozen=True)
class CrossAssetImpulseLabel:
    """One directional gross-return label with an explicit evidence status."""

    bar_open_at: str
    decision_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    leader_symbol: str
    follower_symbol: str
    signal_variant: ImpulseSignalVariant
    anchor: ImpulseAnchor
    direction: ImpulseDirection
    horizon_minutes: int
    entry_price: float | None
    exit_price: float | None
    directional_gross_return_bps: float | None
    status: ImpulseLabelStatus
    report_only: bool = field(default=True, init=False)
    execution_authority: Literal["none"] = field(default="none", init=False)


def _validate_selection_thresholds(config: CrossAssetImpulseConfig) -> None:
    _minimum_integer(config.minimum_events_per_fold, 1, "minimum_events_per_fold")
    _minimum_integer(
        config.minimum_direction_events_per_fold,
        1,
        "minimum_direction_events_per_fold",
    )
    if 2 * config.minimum_direction_events_per_fold > config.minimum_events_per_fold:
        raise ValueError("direction event minima exceed total event minimum")
    for label, value in (
        ("minimum_base_fold_mean_bps", config.minimum_base_fold_mean_bps),
        ("minimum_base_median_fold_mean_bps", config.minimum_base_median_fold_mean_bps),
        ("minimum_direction_mean_bps", config.minimum_direction_mean_bps),
        ("minimum_delayed_fold_mean_bps", config.minimum_delayed_fold_mean_bps),
        (
            "minimum_delayed_median_fold_mean_bps",
            config.minimum_delayed_median_fold_mean_bps,
        ),
        ("minimum_events_per_day", config.minimum_events_per_day),
        ("maximum_p90_interarrival_minutes", config.maximum_p90_interarrival_minutes),
    ):
        _positive(value, label)


def _validate_window(start: pd.Timestamp, end: pd.Timestamp) -> None:
    if start.tz is None or end.tz is None:
        raise ValueError("development window must be timezone-aware")
    if start.tz_convert("UTC") >= end.tz_convert("UTC"):
        raise ValueError("development start must precede end")


def _validate_horizons(horizons: tuple[int, ...]) -> None:
    if not horizons or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in horizons
    ):
        raise ValueError("horizons_minutes must contain positive integers")
    if tuple(sorted(set(horizons))) != horizons:
        raise ValueError("horizons_minutes must be unique and strictly increasing")


def _minimum_integer(value: int, minimum: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer at least {minimum}")


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value < 0.0:
        raise ValueError(f"{label} must be non-negative and finite")
