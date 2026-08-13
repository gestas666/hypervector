"""Typed contracts for report-only cross-sectional breadth research."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal

import pandas as pd

BreadthDirection = Literal["long", "short"]
BreadthSignalVariant = Literal[
    "primary",
    "btc_only_momentum",
    "lagged_breadth_placebo",
]
BreadthAnchor = Literal["base", "delayed"]
BreadthLabelStatus = Literal[
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


def declared_breadth_variants() -> tuple[BreadthSignalVariant, ...]:
    """Return one selectable signal and two fixed nonselectable controls."""
    return ("primary", "btc_only_momentum", "lagged_breadth_placebo")


@dataclass(frozen=True)
class CrossAssetBreadthConfig:
    """Frozen feature, timing, label, and feasibility contract."""

    symbols: tuple[str, ...] = ("BTC", "ETH", "SOL", "HYPE")
    warmup_start: pd.Timestamp = field(
        default_factory=lambda: pd.Timestamp("2025-07-20T23:55:00Z")
    )
    development_start: pd.Timestamp = field(default_factory=lambda: _DEFAULT_START)
    development_end: pd.Timestamp = field(default_factory=lambda: _DEFAULT_END)
    bar_minutes: int = 15
    return_bars: int = 6
    lookback_bars: int = 672
    minimum_valid_bars: int = 666
    breadth_required: int = 3
    dispersion_quantile: float = 0.75
    cooldown_minutes: int = 60
    horizon_minutes: int = 60
    delayed_entry_minutes: int = 1
    placebo_lag_bars: int = 96
    nominal_round_trip_cost_bps: float = 13.0
    stress_round_trip_cost_bps: float = 20.0
    minimum_events_per_fold: int = 30
    minimum_direction_events_per_fold: int = 10
    minimum_events_per_day: float = 1.0
    maximum_p90_interarrival_minutes: float = 4_320.0
    report_only: bool = field(default=True, init=False)
    execution_authority: Literal["none"] = field(default="none", init=False)

    def __post_init__(self) -> None:
        """Reject incoherent research contracts before data inspection."""
        _validate_window(self.warmup_start, self.development_start)
        _validate_window(self.development_start, self.development_end)
        if self.symbols != ("BTC", "ETH", "SOL", "HYPE"):
            raise ValueError("symbols must match the frozen four-asset universe")
        _minimum_integer(self.bar_minutes, 1, "bar_minutes")
        _minimum_integer(self.return_bars, 1, "return_bars")
        _minimum_integer(self.lookback_bars, self.return_bars + 1, "lookback_bars")
        _minimum_integer(self.minimum_valid_bars, 2, "minimum_valid_bars")
        if self.minimum_valid_bars > self.lookback_bars:
            raise ValueError("minimum_valid_bars cannot exceed lookback_bars")
        if not 3 <= self.breadth_required <= len(self.symbols):
            raise ValueError("breadth_required must be three or four")
        if not 0.0 < self.dispersion_quantile < 1.0:
            raise ValueError("dispersion_quantile must be between zero and one")
        _minimum_integer(self.horizon_minutes, 1, "horizon_minutes")
        _minimum_integer(
            self.cooldown_minutes, self.horizon_minutes, "cooldown_minutes"
        )
        _minimum_integer(self.delayed_entry_minutes, 1, "delayed_entry_minutes")
        _minimum_integer(self.placebo_lag_bars, 1, "placebo_lag_bars")
        _positive(self.nominal_round_trip_cost_bps, "nominal cost")
        _positive(self.stress_round_trip_cost_bps, "stress cost")
        if self.stress_round_trip_cost_bps < self.nominal_round_trip_cost_bps:
            raise ValueError("stress cost must not be below nominal cost")
        _minimum_integer(self.minimum_events_per_fold, 1, "minimum_events_per_fold")
        _minimum_integer(
            self.minimum_direction_events_per_fold,
            1,
            "minimum_direction_events_per_fold",
        )
        _positive(self.minimum_events_per_day, "minimum_events_per_day")
        _positive(
            self.maximum_p90_interarrival_minutes,
            "maximum_p90_interarrival_minutes",
        )


def declared_breadth_folds(
    config: CrossAssetBreadthConfig,
) -> tuple[tuple[str, pd.Timestamp, pd.Timestamp], ...]:
    """Return the exact frozen chronological scoring folds."""
    if (
        config.development_start != _DEFAULT_START
        or config.development_end != _DEFAULT_END
    ):
        raise ValueError("breadth development folds are fixed")
    return _DEFAULT_FOLDS


@dataclass(frozen=True)
class CrossAssetBreadthEvent:
    """One causal breadth-expansion event under a primary or control signal."""

    bar_open_at: str
    decision_time_utc: str
    entry_time_utc: str
    signal_variant: BreadthSignalVariant
    direction: BreadthDirection
    btc_normalized_return: float
    breadth_count: int
    dispersion: float
    dispersion_threshold: float
    valid_symbols: int
    report_only: bool = field(default=True, init=False)
    execution_authority: Literal["none"] = field(default="none", init=False)


@dataclass(frozen=True)
class CrossAssetBreadthLabel:
    """One BTC directional gross-return label with explicit evidence status."""

    bar_open_at: str
    decision_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    signal_variant: BreadthSignalVariant
    anchor: BreadthAnchor
    direction: BreadthDirection
    horizon_minutes: int
    entry_price: float | None
    exit_price: float | None
    directional_gross_return_bps: float | None
    status: BreadthLabelStatus
    report_only: bool = field(default=True, init=False)
    execution_authority: Literal["none"] = field(default="none", init=False)


def _validate_window(start: pd.Timestamp, end: pd.Timestamp) -> None:
    if start.tz is None or end.tz is None:
        raise ValueError("development window must be timezone-aware")
    if start.tz_convert("UTC") >= end.tz_convert("UTC"):
        raise ValueError("development start must precede end")


def _minimum_integer(value: int, minimum: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer at least {minimum}")


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
