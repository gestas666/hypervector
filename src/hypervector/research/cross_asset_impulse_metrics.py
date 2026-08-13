"""Metrics and cadence calculations for cross-asset impulse evidence."""

from __future__ import annotations

import math
import statistics

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    CrossAssetImpulseLabel,
    ImpulseLabelStatus,
)

type Fold = tuple[str, pd.Timestamp, pd.Timestamp]
type Cell = dict[str, object]

_EXCLUSIONS = ("technical_gap", "fold_boundary_purged", "right_censored")


def build_fold_payloads(
    labels: tuple[CrossAssetImpulseLabel, ...],
    folds: tuple[Fold, ...],
    config: CrossAssetImpulseConfig,
) -> list[Cell]:
    """Return base and delayed metrics for every chronological fold."""
    return [_fold_payload(fold, labels, config) for fold in folds]


def impulse_direction_means(
    labels: tuple[CrossAssetImpulseLabel, ...],
    folds: tuple[Fold, ...],
    config: CrossAssetImpulseConfig,
) -> dict[str, float | None]:
    """Return resolved development-wide base means by direction."""
    grouped: dict[str, list[float]] = {"long": [], "short": []}
    for label in labels:
        fold = _containing_fold(_time(label.decision_time_utc), folds)
        if (
            label.anchor == "base"
            and fold
            and _status(label, fold[2], config) == "resolved"
        ):
            grouped[label.direction].append(float(label.directional_gross_return_bps))
    return {direction: _mean(values) for direction, values in grouped.items()}


def impulse_cadence(
    labels: tuple[CrossAssetImpulseLabel, ...],
    folds: tuple[Fold, ...],
    config: CrossAssetImpulseConfig,
) -> Cell:
    """Return de-duplicated resolved primary-event cadence diagnostics."""
    times = sorted(
        {
            _time(label.decision_time_utc)
            for label in labels
            if label.anchor == "base" and _resolves(label, folds, config)
        }
    )
    days = calendar_days(config)
    intervals = [
        (right - left).total_seconds() / 60
        for left, right in zip(times[:-1], times[1:], strict=True)
    ]
    return {
        "resolved_events": len(times),
        "calendar_days": days,
        "events_per_calendar_day": len(times) / days,
        "active_utc_day_fraction": len({time.normalize() for time in times}) / days,
        "median_interarrival_minutes": _median(intervals),
        "p90_interarrival_minutes": _quantile(intervals, 0.9),
        "maximum_interarrival_minutes": max(intervals) if intervals else None,
        "rolling_three_day_coverage": _three_day_coverage(times, config),
        "longest_eventless_minutes": _longest_eventless(times, config),
    }


def calendar_days(config: CrossAssetImpulseConfig) -> int:
    """Return the count of UTC calendar-day starts in development."""
    return len(
        pd.date_range(
            config.development_start.normalize(),
            config.development_end.normalize(),
            freq="1D",
            inclusive="left",
        )
    )


def median_metric_means(metrics: list[Cell]) -> float | None:
    """Return the median of complete fold means, otherwise unavailable."""
    values = [metric["mean_gross_bps"] for metric in metrics]
    if not all(value is not None for value in values):
        return None
    return _median([float(value) for value in values])


def minimum_metric_means(metrics: list[Cell]) -> float | None:
    """Return the minimum of complete fold means, otherwise unavailable."""
    values = [metric["mean_gross_bps"] for metric in metrics]
    if not values or not all(value is not None for value in values):
        return None
    return min(float(value) for value in values)


def _fold_payload(
    fold: Fold,
    labels: tuple[CrossAssetImpulseLabel, ...],
    config: CrossAssetImpulseConfig,
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
    labels: tuple[CrossAssetImpulseLabel, ...],
    anchor: str,
    fold_end: pd.Timestamp,
    config: CrossAssetImpulseConfig,
) -> Cell:
    selected = tuple(label for label in labels if label.anchor == anchor)
    resolved = tuple(
        label for label in selected if _status(label, fold_end, config) == "resolved"
    )
    values = [float(label.directional_gross_return_bps) for label in resolved]
    mean = _mean(values)
    payload: Cell = {
        "resolved_events": len(resolved),
        "excluded": _excluded_counts(selected, fold_end, config),
        "long_events": sum(label.direction == "long" for label in resolved),
        "short_events": sum(label.direction == "short" for label in resolved),
        "mean_gross_bps": mean,
        "median_gross_bps": _median(values),
        "trimmed_mean_gross_bps": _trimmed_mean(values),
        "std_gross_bps": _sample_std(values),
        "mean_minus_nominal_bps": _subtract(mean, config.nominal_round_trip_cost_bps),
        "mean_minus_stress_bps": _subtract(mean, config.stress_round_trip_cost_bps),
    }
    _add_distribution_metrics(payload, values)
    return payload


def _excluded_counts(
    labels: tuple[CrossAssetImpulseLabel, ...],
    fold_end: pd.Timestamp,
    config: CrossAssetImpulseConfig,
) -> dict[str, int]:
    return {
        status: sum(_status(label, fold_end, config) == status for label in labels)
        for status in _EXCLUSIONS
    }


def _add_distribution_metrics(payload: Cell, values: list[float]) -> None:
    for name, quantile in (
        ("p10", 0.1),
        ("p25", 0.25),
        ("p75", 0.75),
        ("p90", 0.9),
    ):
        payload[f"{name}_gross_bps"] = _quantile(values, quantile)
    for threshold in (0, 13, 20, 26):
        payload[f"fraction_above_{threshold}_bps"] = (
            sum(value > threshold for value in values) / len(values) if values else None
        )


def _status(
    label: CrossAssetImpulseLabel,
    fold_end: pd.Timestamp,
    config: CrossAssetImpulseConfig,
) -> ImpulseLabelStatus:
    if label.status != "resolved":
        return label.status
    exit_time = _time(label.exit_time_utc)
    if exit_time >= config.development_end:
        return "right_censored"
    return "fold_boundary_purged" if exit_time >= fold_end else "resolved"


def _resolves(
    label: CrossAssetImpulseLabel,
    folds: tuple[Fold, ...],
    config: CrossAssetImpulseConfig,
) -> bool:
    fold = _containing_fold(_time(label.decision_time_utc), folds)
    return fold is not None and _status(label, fold[2], config) == "resolved"


def _containing_fold(timestamp: pd.Timestamp, folds: tuple[Fold, ...]) -> Fold | None:
    return next((fold for fold in folds if fold[1] <= timestamp < fold[2]), None)


def _three_day_coverage(
    times: list[pd.Timestamp], config: CrossAssetImpulseConfig
) -> float | None:
    starts = pd.date_range(
        config.development_start.normalize(),
        config.development_end.normalize() - pd.Timedelta(days=3),
        freq="1D",
    )
    if not len(starts):
        return None
    hits = sum(
        any(start <= time < start + pd.Timedelta(days=3) for time in times)
        for start in starts
    )
    return hits / len(starts)


def _longest_eventless(
    times: list[pd.Timestamp], config: CrossAssetImpulseConfig
) -> float:
    boundaries = [config.development_start, *times, config.development_end]
    return max(
        (right - left).total_seconds() / 60
        for left, right in zip(boundaries[:-1], boundaries[1:], strict=True)
    )


def _mean(values: list[float]) -> float | None:
    return float(statistics.fmean(values)) if values else None


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _trimmed_mean(values: list[float]) -> float | None:
    if not values:
        return None
    ordered, trim = sorted(values), math.floor(len(values) * 0.1)
    return _mean(ordered[trim : len(ordered) - trim] if trim else ordered)


def _sample_std(values: list[float]) -> float | None:
    return float(np.std(values, ddof=1)) if len(values) > 1 else None


def _quantile(values: list[float], quantile: float) -> float | None:
    return float(np.quantile(values, quantile, method="linear")) if values else None


def _subtract(value: float | None, cost: float) -> float | None:
    return value - cost if value is not None else None


def _time(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("impulse timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")
