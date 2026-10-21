"""Metric value validation and explicit availability accounting.

A provider declares point-in-time metric unavailability in its readiness
metrics: with ``metric_availability = "warmup_unavailable"`` every metric it
reports as null is counted as declared unavailable rather than as a telemetry
gap. Callers can also pass explicit metric names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

MetricValue = str | int | float | bool | None

METRIC_AVAILABILITY_KEY = "metric_availability"
METRIC_WARMUP_UNAVAILABLE = "warmup_unavailable"


class MetricAvailability:
    """Track declared unavailability separately from missing telemetry."""

    def __init__(self, horizons: Sequence[int]) -> None:
        """Create counters for the configured horizon identities."""
        self._evaluations: dict[str, int] = {}
        self._horizons: dict[int, dict[str, int]] = {
            horizon: {} for horizon in horizons
        }

    def observe_evaluation(
        self,
        metrics: Mapping[str, object],
        explicitly_unavailable: frozenset[str] = frozenset(),
    ) -> frozenset[str]:
        """Record and return metrics declared unavailable for one evaluation."""
        unavailable = _explicitly_unavailable(metrics).union(
            _validated_unavailable(metrics, explicitly_unavailable)
        )
        for name in unavailable:
            self._evaluations[name] = self._evaluations.get(name, 0) + 1
        return unavailable

    def observe_horizon(
        self,
        metrics: Mapping[str, object],
        horizon: int,
        explicitly_unavailable: frozenset[str] = frozenset(),
    ) -> frozenset[str]:
        """Record and return unavailable metrics for one horizon observation."""
        unavailable = _explicitly_unavailable(metrics).union(
            _validated_unavailable(metrics, explicitly_unavailable)
        )
        for name in unavailable:
            values = self._horizons[horizon]
            values[name] = values.get(name, 0) + 1
        return unavailable

    def prior_evaluation_gaps(self, name: str, calls: int) -> int:
        """Return earlier calls not covered by explicit unavailability."""
        return calls - self._evaluations.get(name, 0)

    def prior_horizon_gaps(self, name: str, horizon: int, calls: int) -> int:
        """Return earlier horizon calls not declared unavailable."""
        return calls - self._horizons[horizon].get(name, 0)


def usable_metrics(metrics: Mapping[str, object]) -> dict[str, MetricValue]:
    """Validate and normalize one provider metric mapping."""
    output: dict[str, MetricValue] = {}
    for raw_name, raw_value in metrics.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("metric names must be non-empty text")
        name = raw_name.strip()
        if raw_value is None:
            continue
        if not isinstance(raw_value, (str, int, float, bool)):
            raise ValueError(f"metric {raw_name} has an unsupported value")
        metric_type(raw_value)
        output[name] = raw_value
    return output


def metric_type(value: MetricValue) -> tuple[str, str]:
    """Return the stable diagnostic kind and JSON value type."""
    if isinstance(value, bool):
        return "categorical", "bool"
    if isinstance(value, int):
        return "categorical", "int"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("numeric metric values must be finite")
        return "numeric", "float"
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("categorical metric values must be non-empty")
        return "categorical", "str"
    raise ValueError("metric has an unsupported value")


def _explicitly_unavailable(metrics: Mapping[str, object]) -> frozenset[str]:
    if metrics.get(METRIC_AVAILABILITY_KEY) != METRIC_WARMUP_UNAVAILABLE:
        return frozenset()
    return frozenset(
        name for name, value in metrics.items() if isinstance(name, str) and value is None
    )


def _validated_unavailable(
    metrics: Mapping[str, object], names: frozenset[str]
) -> frozenset[str]:
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("explicitly unavailable metric names must be non-empty")
        if name not in metrics or metrics.get(name) is not None:
            raise ValueError(
                "explicitly unavailable metrics must be present with null values"
            )
    return names
