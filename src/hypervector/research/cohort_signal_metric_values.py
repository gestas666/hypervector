"""Metric value validation and explicit availability accounting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

MetricValue = str | int | float | bool | None

_EXPLICIT_UNAVAILABLE_CATEGORIES = frozenset({"breakout_side"})
_CONDITION_ANATOMY_STATUS = "condition_anatomy_status"
_CONDITION_ANATOMY_UNAVAILABLE = "legacy_or_warmup_unavailable"
_PRESSURE_UNAVAILABLE_STATUSES = frozenset({"no_candidate", "stale_candidate"})
_PRESSURE_METRICS = frozenset({"imbalance_10", "pressure_age_seconds"})
_CONDITION_ANATOMY_METRICS = frozenset(
    {
        "close",
        "ema_fast_period",
        "ema_gap_bps",
        "ema_slow_period",
        "fast_ema",
        "long_breakout_distance_bps",
        "long_ema_alignment",
        "long_pressure_confirmation",
        "long_price_breakout",
        "long_raw_condition",
        "prior_breakout_high",
        "prior_breakout_low",
        "short_breakout_distance_bps",
        "short_ema_alignment",
        "short_pressure_confirmation",
        "short_price_breakout",
        "short_raw_condition",
        "slow_ema",
    }
)


class MetricAvailability:
    """Track declared unavailability separately from missing telemetry."""

    def __init__(self, horizons: Sequence[int]) -> None:
        """Create counters for the configured horizon identities."""
        self._evaluations = dict.fromkeys(_CONDITION_ANATOMY_METRICS, 0)
        self._horizons = {
            horizon: dict.fromkeys(_CONDITION_ANATOMY_METRICS, 0)
            for horizon in horizons
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
            if name not in _EXPLICIT_UNAVAILABLE_CATEGORIES:
                continue
            raw_value = "unavailable"
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
    unavailable: set[str] = set()
    if metrics.get(_CONDITION_ANATOMY_STATUS) == _CONDITION_ANATOMY_UNAVAILABLE:
        unavailable.update(
            name for name in _CONDITION_ANATOMY_METRICS if metrics.get(name) is None
        )
    if metrics.get("pressure_status") in _PRESSURE_UNAVAILABLE_STATUSES:
        unavailable.update(
            name for name in _PRESSURE_METRICS if metrics.get(name) is None
        )
    return frozenset(unavailable)


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
