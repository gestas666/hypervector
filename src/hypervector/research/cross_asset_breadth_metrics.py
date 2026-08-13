"""Fold, distribution, direction, and cadence metrics for breadth labels."""

from __future__ import annotations

import math
import statistics

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_breadth_models import (
    BreadthAnchor,
    CrossAssetBreadthConfig,
    CrossAssetBreadthLabel,
)

type Fold = tuple[str, pd.Timestamp, pd.Timestamp]
type Cell = dict[str, object]

_EXCLUSIONS = ("technical_gap", "fold_boundary_purged", "right_censored")


def build_breadth_cell(
    labels: tuple[CrossAssetBreadthLabel, ...],
    folds: tuple[Fold, ...],
    config: CrossAssetBreadthConfig,
) -> Cell:
    """Aggregate one signal variant without changing its event population."""
    fold_payloads = [_fold_payload(fold, labels, config) for fold in folds]
    return {
        "signal_variant": labels[0].signal_variant if labels else None,
        "horizon_minutes": config.horizon_minutes,
        "folds": fold_payloads,
        "pooled": {
            anchor: _metrics(labels, anchor, None, config)
            for anchor in ("base", "delayed")
        },
        "direction_means_bps": _direction_means(labels),
        "cadence": _cadence(labels, config),
        "report_only": True,
        "execution_authority": "none",
    }


def apply_breadth_eligibility(
    primary: Cell,
    controls: list[Cell],
    config: CrossAssetBreadthConfig,
) -> None:
    """Attach failures for every frozen feasibility and control criterion."""
    failures: list[str] = []
    folds = _fold_metrics(primary)
    if any(
        item["base"]["resolved_events"] < config.minimum_events_per_fold
        for item in folds
    ):
        failures.append("insufficient_events_per_fold")
    if _direction_counts_fail(folds, config.minimum_direction_events_per_fold):
        failures.append("insufficient_direction_events_per_fold")
    cadence = _mapping(primary["cadence"])
    if float(cadence["events_per_calendar_day"]) < config.minimum_events_per_day:
        failures.append("insufficient_event_cadence")
    gap = cadence["p90_interarrival_minutes"]
    if gap is None or float(gap) > config.maximum_p90_interarrival_minutes:
        failures.append("p90_event_gap_too_large")
    _add_economic_failures(failures, primary, config)
    if not _dominates_controls(folds, controls):
        failures.append("delayed_primary_does_not_dominate_controls_every_fold")
    primary["eligibility_failures"] = failures
    primary["eligible_for_replay"] = not failures
    primary["selected_for_replay"] = not failures


def _add_economic_failures(
    failures: list[str],
    primary: Cell,
    config: CrossAssetBreadthConfig,
) -> None:
    folds = _fold_metrics(primary)
    cost = config.nominal_round_trip_cost_bps
    if not _all_fold_means_above(folds, "base", cost):
        failures.append("base_fold_mean_not_above_nominal_cost")
    if not _all_fold_means_above(folds, "delayed", cost):
        failures.append("delayed_fold_mean_not_above_nominal_cost")
    pooled = _mapping(primary["pooled"])
    for anchor in ("base", "delayed"):
        metrics = _mapping(pooled[anchor])
        if not _above(metrics["median_gross_bps"], 0.0):
            failures.append(f"{anchor}_pooled_median_not_positive")
        if not _above(metrics["trimmed_mean_gross_bps"], cost):
            failures.append(f"{anchor}_pooled_trimmed_mean_not_above_cost")
    directions = _mapping(primary["direction_means_bps"])
    if any(not _above(directions[direction], cost) for direction in ("long", "short")):
        failures.append("direction_mean_not_above_nominal_cost")


def _fold_payload(
    fold: Fold,
    labels: tuple[CrossAssetBreadthLabel, ...],
    config: CrossAssetBreadthConfig,
) -> Cell:
    name, start, end = fold
    selected = tuple(
        label for label in labels if start <= _time(label.decision_time_utc) < end
    )
    return {
        "fold": name,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "base": _metrics(selected, "base", end, config),
        "delayed": _metrics(selected, "delayed", end, config),
    }


def _metrics(
    labels: tuple[CrossAssetBreadthLabel, ...],
    anchor: BreadthAnchor,
    fold_end: pd.Timestamp | None,
    config: CrossAssetBreadthConfig,
) -> Cell:
    selected = tuple(label for label in labels if label.anchor == anchor)
    resolved = tuple(
        label for label in selected if _status(label, fold_end, config) == "resolved"
    )
    values = [float(label.directional_gross_return_bps) for label in resolved]
    mean = _mean(values)
    return {
        "resolved_events": len(resolved),
        "long_events": sum(label.direction == "long" for label in resolved),
        "short_events": sum(label.direction == "short" for label in resolved),
        "excluded": _excluded_counts(selected, fold_end, config),
        "mean_gross_bps": mean,
        "median_gross_bps": _median(values),
        "trimmed_mean_gross_bps": _trimmed_mean(values),
        "std_gross_bps": float(np.std(values, ddof=1)) if len(values) > 1 else None,
        "mean_minus_nominal_bps": None
        if mean is None
        else mean - config.nominal_round_trip_cost_bps,
        "mean_minus_stress_bps": None
        if mean is None
        else mean - config.stress_round_trip_cost_bps,
        "fraction_above_13_bps": _fraction_above(values, 13.0),
        "fraction_above_20_bps": _fraction_above(values, 20.0),
    }


def _cadence(
    labels: tuple[CrossAssetBreadthLabel, ...],
    config: CrossAssetBreadthConfig,
) -> Cell:
    times = sorted(
        {
            _time(label.decision_time_utc)
            for label in labels
            if label.anchor == "base" and label.status == "resolved"
        }
    )
    intervals = [
        (right - left).total_seconds() / 60.0
        for left, right in zip(times[:-1], times[1:], strict=True)
    ]
    days = len(
        pd.date_range(
            config.development_start.normalize(),
            config.development_end.normalize(),
            freq="1D",
            inclusive="left",
        )
    )
    return {
        "resolved_events": len(times),
        "calendar_days": days,
        "events_per_calendar_day": len(times) / days,
        "median_interarrival_minutes": _median(intervals),
        "p90_interarrival_minutes": _quantile(intervals, 0.9),
        "maximum_interarrival_minutes": max(intervals) if intervals else None,
    }


def _direction_means(
    labels: tuple[CrossAssetBreadthLabel, ...],
) -> dict[str, float | None]:
    return {
        direction: _mean(
            [
                float(label.directional_gross_return_bps)
                for label in labels
                if label.anchor == "base"
                and label.status == "resolved"
                and label.direction == direction
            ]
        )
        for direction in ("long", "short")
    }


def _dominates_controls(primary_folds: list[Cell], controls: list[Cell]) -> bool:
    if len(controls) != 2:
        return False
    for index, primary_fold in enumerate(primary_folds):
        primary_mean = _mapping(primary_fold["delayed"])["mean_gross_bps"]
        for control in controls:
            control_fold = _fold_metrics(control)[index]
            control_mean = _mapping(control_fold["delayed"])["mean_gross_bps"]
            if (
                primary_mean is None
                or control_mean is None
                or float(primary_mean) <= float(control_mean)
            ):
                return False
    return True


def _direction_counts_fail(folds: list[Cell], minimum: int) -> bool:
    return any(
        int(_mapping(fold["base"])[f"{direction}_events"]) < minimum
        for fold in folds
        for direction in ("long", "short")
    )


def _all_fold_means_above(folds: list[Cell], anchor: str, threshold: float) -> bool:
    return all(
        _above(_mapping(fold[anchor])["mean_gross_bps"], threshold) for fold in folds
    )


def _status(
    label: CrossAssetBreadthLabel,
    fold_end: pd.Timestamp | None,
    config: CrossAssetBreadthConfig,
) -> str:
    if label.status != "resolved":
        return label.status
    exit_time = _time(label.exit_time_utc)
    if exit_time >= config.development_end:
        return "right_censored"
    if fold_end is not None and exit_time >= fold_end:
        return "fold_boundary_purged"
    return "resolved"


def _excluded_counts(
    labels: tuple[CrossAssetBreadthLabel, ...],
    fold_end: pd.Timestamp | None,
    config: CrossAssetBreadthConfig,
) -> dict[str, int]:
    return {
        status: sum(_status(label, fold_end, config) == status for label in labels)
        for status in _EXCLUSIONS
    }


def _fold_metrics(cell: Cell) -> list[Cell]:
    value = cell["folds"]
    if not isinstance(value, list):
        raise TypeError("breadth cell folds must be a list")
    return [_mapping(item) for item in value]


def _mapping(value: object) -> Cell:
    if not isinstance(value, dict):
        raise TypeError("breadth metric payload must be a mapping")
    return value


def _above(value: object, threshold: float) -> bool:
    return (
        value is not None and math.isfinite(float(value)) and float(value) > threshold
    )


def _mean(values: list[float]) -> float | None:
    return float(statistics.fmean(values)) if values else None


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _trimmed_mean(values: list[float]) -> float | None:
    if not values:
        return None
    trim = math.floor(len(values) * 0.1)
    ordered = sorted(values)
    return _mean(ordered[trim : len(ordered) - trim] if trim else ordered)


def _quantile(values: list[float], quantile: float) -> float | None:
    return float(np.quantile(values, quantile, method="linear")) if values else None


def _fraction_above(values: list[float], threshold: float) -> float | None:
    return sum(value > threshold for value in values) / len(values) if values else None


def _time(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("breadth timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")
