"""Bounded causal summaries of exact provider decision-time metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math

_MINUTE_MS = 60_000
_VALID_STATUSES = frozenset({"resolved", "censored", "missing_data"})
_EXPLICIT_UNAVAILABLE_CATEGORIES = frozenset({"breakout_side"})
_MetricValue = str | int | float | bool | None
_CategoryKey = tuple[str, str]


@dataclass
class _NumericStats:
    count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    @property
    def mean(self) -> float | None:
        return self.total / self.count if self.count else None


@dataclass
class _NumericOutcome:
    count: int = 0
    metric_total: float = 0.0
    return_total: float = 0.0

    def observe(self, metric: float, directional_return_bps: float) -> None:
        self.count += 1
        self.metric_total += metric
        self.return_total += directional_return_bps

    def as_payload(self) -> dict[str, object]:
        return {
            "count": self.count,
            "mean_metric": self.metric_total / self.count if self.count else None,
            "mean_directional_return_bps": (
                self.return_total / self.count if self.count else None
            ),
        }


@dataclass
class _CategoryStats:
    value: str | int | bool
    count: int = 0
    positive: int = 0
    return_total: float = 0.0
    decision_times_ms: list[int] = field(default_factory=list)

    def observe_value(self) -> None:
        self.count += 1

    def observe_outcome(
        self, decision_time_ms: int, directional_return_bps: float
    ) -> None:
        self.count += 1
        self.positive += directional_return_bps > 0.0
        self.return_total += directional_return_bps
        self.decision_times_ms.append(decision_time_ms)

    def outcome_payload(self, horizon_minutes: int) -> dict[str, object]:
        return {
            "value": self.value,
            "resolved": self.count,
            "non_overlapping_resolved": _non_overlapping_count(
                self.decision_times_ms, horizon_minutes
            ),
            "positive_directional_rate": (
                self.positive / self.count if self.count else None
            ),
            "mean_directional_return_bps": (
                self.return_total / self.count if self.count else None
            ),
        }


@dataclass
class _CategoryOnsetStats:
    value: str | int | bool
    resolved: int = 0
    positive: int = 0
    return_total: float = 0.0
    censored: int = 0
    missing_data: int = 0
    decision_times_ms: list[int] = field(default_factory=list)

    def observe(
        self,
        status: str,
        decision_time_ms: int,
        directional_return_bps: float | None,
    ) -> None:
        if status == "censored":
            self.censored += 1
        elif status == "missing_data":
            self.missing_data += 1
        elif directional_return_bps is not None:
            self.resolved += 1
            self.positive += directional_return_bps > 0.0
            self.return_total += directional_return_bps
            self.decision_times_ms.append(decision_time_ms)

    def as_payload(self, horizon_minutes: int) -> dict[str, object]:
        return {
            "value": self.value,
            "resolved": self.resolved,
            "non_overlapping_resolved": _non_overlapping_count(
                self.decision_times_ms, horizon_minutes
            ),
            "censored": self.censored,
            "missing_data": self.missing_data,
            "positive_directional_rate": (
                self.positive / self.resolved if self.resolved else None
            ),
            "mean_directional_return_bps": (
                self.return_total / self.resolved if self.resolved else None
            ),
        }


@dataclass
class _MetricHorizon:
    resolved: int = 0
    censored: int = 0
    missing_data: int = 0
    metric_missing: int = 0
    positive: int = 0
    decision_times_ms: list[int] = field(default_factory=list)
    positive_numeric: _NumericOutcome = field(default_factory=_NumericOutcome)
    nonpositive_numeric: _NumericOutcome = field(default_factory=_NumericOutcome)
    category_outcomes: dict[_CategoryKey, _CategoryStats] = field(default_factory=dict)
    category_onsets: dict[_CategoryKey, _CategoryOnsetStats] = field(
        default_factory=dict
    )
    last_category_key: _CategoryKey | None = None


@dataclass
class _MetricEvidence:
    kind: str
    value_type: str
    horizons: dict[int, _MetricHorizon]
    observations: int = 0
    missing_evaluations: int = 0
    numeric: _NumericStats = field(default_factory=_NumericStats)
    categories: dict[_CategoryKey, _CategoryStats] = field(default_factory=dict)


class MetricDiagnosticsAccumulator:
    """Accumulate exact metrics and future labels without retaining candle paths."""

    def __init__(self, horizons_minutes: Sequence[int]) -> None:
        """Create one provider-local accumulator for fixed positive horizons."""
        horizons = tuple(horizons_minutes)
        if not horizons or len(set(horizons)) != len(horizons):
            raise ValueError("metric horizons must be unique and non-empty")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in horizons
        ):
            raise ValueError("metric horizons must be positive integer minutes")
        self._horizons = tuple(sorted(horizons))
        self._metrics: dict[str, _MetricEvidence] = {}
        self._horizon_calls = dict.fromkeys(self._horizons, 0)
        self._last_decision_time_ms: dict[int, int | None] = dict.fromkeys(
            self._horizons
        )
        self._evaluations = 0
        self._evaluations_with_metrics = 0

    def observe_evaluation(self, metrics: Mapping[str, object]) -> None:
        """Observe one deduplicated evaluation's point-in-time metric mapping."""
        usable = _usable_metrics(metrics)
        prior_evaluations = self._evaluations
        self._evaluations += 1
        self._evaluations_with_metrics += bool(usable)
        for name, evidence in self._metrics.items():
            if name not in usable:
                evidence.missing_evaluations += 1
        for name, value in usable.items():
            evidence = self._metrics.get(name)
            if evidence is None:
                evidence = self._new_metric(name, value, prior_evaluations)
            _observe_metric_value(name, evidence, value)

    def observe_horizon(
        self,
        metrics: Mapping[str, object],
        *,
        horizon_minutes: int,
        decision_time_ms: int,
        status: str,
        directional_return_bps: float | None,
    ) -> None:
        """Pair one metric map with an existing causal horizon resolution."""
        _validate_horizon_observation(
            self._horizons,
            horizon_minutes,
            decision_time_ms,
            status,
            directional_return_bps,
        )
        usable = _usable_metrics(metrics)
        unknown = set(usable).difference(self._metrics)
        if unknown:
            raise ValueError("metric horizon observed before its evaluation")
        self._advance_decision_time(horizon_minutes, decision_time_ms)
        self._horizon_calls[horizon_minutes] += 1
        for name, evidence in self._metrics.items():
            horizon = evidence.horizons[horizon_minutes]
            value = usable.get(name)
            if value is None:
                horizon.metric_missing += 1
                if evidence.kind == "categorical":
                    horizon.last_category_key = None
                continue
            _validate_metric_type(name, evidence, value)
            _observe_metric_horizon(
                evidence,
                horizon,
                value,
                decision_time_ms,
                status,
                directional_return_bps,
            )

    def _advance_decision_time(self, horizon: int, decision_time_ms: int) -> None:
        prior = self._last_decision_time_ms[horizon]
        if prior is not None and decision_time_ms <= prior:
            raise ValueError("metric decision times must be strictly increasing")
        self._last_decision_time_ms[horizon] = decision_time_ms

    def as_payload(self) -> dict[str, object]:
        """Return deterministic JSON-safe descriptive evidence."""
        gaps = sum(value.missing_evaluations for value in self._metrics.values())
        without = self._evaluations - self._evaluations_with_metrics
        return {
            "coverage": {
                "complete": without == 0 and gaps == 0,
                "evaluations_with_metrics": self._evaluations_with_metrics,
                "evaluations_without_metrics": without,
                "metric_value_gaps": gaps,
            },
            "metrics": {
                name: _metric_payload(value)
                for name, value in sorted(self._metrics.items())
            },
        }

    def _new_metric(
        self, name: str, value: _MetricValue, prior_evaluations: int
    ) -> _MetricEvidence:
        kind, value_type = _metric_type(value)
        evidence = _MetricEvidence(
            kind=kind,
            value_type=value_type,
            horizons={
                value: _MetricHorizon(metric_missing=self._horizon_calls[value])
                for value in self._horizons
            },
            missing_evaluations=prior_evaluations,
        )
        self._metrics[name] = evidence
        return evidence


def _usable_metrics(metrics: Mapping[str, object]) -> dict[str, _MetricValue]:
    output: dict[str, _MetricValue] = {}
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
        _metric_type(raw_value)
        output[name] = raw_value
    return output


def _metric_type(value: _MetricValue) -> tuple[str, str]:
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


def _observe_metric_value(
    name: str, evidence: _MetricEvidence, value: _MetricValue
) -> None:
    _validate_metric_type(name, evidence, value)
    evidence.observations += 1
    if evidence.kind == "numeric":
        evidence.numeric.observe(float(value))
        return
    key = _category_key(value)
    category = evidence.categories.setdefault(
        key, _CategoryStats(value=_categorical_value(value))
    )
    category.observe_value()


def _validate_metric_type(
    name: str, evidence: _MetricEvidence, value: _MetricValue
) -> None:
    kind, value_type = _metric_type(value)
    if kind != evidence.kind or value_type != evidence.value_type:
        raise ValueError(
            f"metric {name} changed type from {evidence.value_type} to {value_type}"
        )


def _category_key(value: _MetricValue) -> _CategoryKey:
    _, value_type = _metric_type(value)
    if isinstance(value, bool):
        encoded = "1" if value else "0"
    else:
        encoded = str(value)
    return value_type, encoded


def _categorical_value(value: _MetricValue) -> str | int | bool:
    if isinstance(value, (str, int, bool)) and not isinstance(value, float):
        return value
    raise ValueError("categorical metric has a non-categorical value")


def _validate_horizon_observation(
    horizons: Sequence[int],
    horizon: int,
    decision_time_ms: int,
    status: str,
    directional_return_bps: float | None,
) -> None:
    if horizon not in horizons:
        raise ValueError("metric outcome horizon is not configured")
    if (
        isinstance(decision_time_ms, bool)
        or not isinstance(decision_time_ms, int)
        or decision_time_ms < 0
    ):
        raise ValueError("metric outcome decision time must be nonnegative")
    if status not in _VALID_STATUSES:
        raise ValueError("metric outcome status is invalid")
    if status == "resolved":
        if directional_return_bps is None or not math.isfinite(directional_return_bps):
            raise ValueError("resolved metric outcome requires a finite return")
    elif directional_return_bps is not None:
        raise ValueError("unresolved metric outcome cannot carry a return")


def _observe_metric_horizon(
    evidence: _MetricEvidence,
    horizon: _MetricHorizon,
    value: _MetricValue,
    decision_time_ms: int,
    status: str,
    directional_return_bps: float | None,
) -> None:
    if evidence.kind == "categorical":
        _observe_categorical_onset(
            horizon,
            value,
            decision_time_ms,
            status,
            directional_return_bps,
        )
    if status == "censored":
        horizon.censored += 1
        return
    if status == "missing_data":
        horizon.missing_data += 1
        return
    if directional_return_bps is None:
        raise ValueError("resolved metric outcome requires a return")
    horizon.resolved += 1
    horizon.positive += directional_return_bps > 0.0
    horizon.decision_times_ms.append(decision_time_ms)
    if evidence.kind == "numeric":
        target = (
            horizon.positive_numeric
            if directional_return_bps > 0.0
            else horizon.nonpositive_numeric
        )
        target.observe(float(value), directional_return_bps)
        return
    key = _category_key(value)
    category = horizon.category_outcomes.setdefault(
        key, _CategoryStats(value=_categorical_value(value))
    )
    category.observe_outcome(decision_time_ms, directional_return_bps)


def _observe_categorical_onset(
    horizon: _MetricHorizon,
    value: _MetricValue,
    decision_time_ms: int,
    status: str,
    directional_return_bps: float | None,
) -> None:
    key = _category_key(value)
    is_onset = key != horizon.last_category_key
    horizon.last_category_key = key
    if not is_onset:
        return
    onset = horizon.category_onsets.setdefault(
        key, _CategoryOnsetStats(value=_categorical_value(value))
    )
    onset.observe(status, decision_time_ms, directional_return_bps)


def _metric_payload(evidence: _MetricEvidence) -> dict[str, object]:
    output: dict[str, object] = {
        "kind": evidence.kind,
        "value_type": evidence.value_type,
        "observations": evidence.observations,
        "missing_evaluations": evidence.missing_evaluations,
        "horizons": {
            str(value): _horizon_payload(item, value, evidence.kind)
            for value, item in sorted(evidence.horizons.items())
        },
    }
    if evidence.kind == "numeric":
        output.update(
            {
                "minimum": evidence.numeric.minimum,
                "mean": evidence.numeric.mean,
                "maximum": evidence.numeric.maximum,
            }
        )
    else:
        output["categories"] = [
            {"value": item.value, "count": item.count}
            for _, item in sorted(evidence.categories.items())
        ]
    return output


def _horizon_payload(
    horizon: _MetricHorizon, horizon_minutes: int, kind: str
) -> dict[str, object]:
    output: dict[str, object] = {
        "resolved": horizon.resolved,
        "non_overlapping_resolved": _non_overlapping_count(
            horizon.decision_times_ms, horizon_minutes
        ),
        "censored": horizon.censored,
        "missing_data": horizon.missing_data,
        "metric_missing": horizon.metric_missing,
        "positive_directional_rate": (
            horizon.positive / horizon.resolved if horizon.resolved else None
        ),
    }
    if kind == "numeric":
        output["positive_directional"] = horizon.positive_numeric.as_payload()
        output["nonpositive_directional"] = horizon.nonpositive_numeric.as_payload()
    else:
        output["by_value"] = [
            item.outcome_payload(horizon_minutes)
            for _, item in sorted(horizon.category_outcomes.items())
        ]
        output["by_value_onset"] = [
            item.as_payload(horizon_minutes)
            for _, item in sorted(horizon.category_onsets.items())
        ]
    return output


def _non_overlapping_count(
    decision_times_ms: Sequence[int], horizon_minutes: int
) -> int:
    count = 0
    next_available = -1
    for decision_time_ms in sorted(decision_times_ms):
        if decision_time_ms < next_available:
            continue
        count += 1
        next_available = decision_time_ms + horizon_minutes * _MINUTE_MS
    return count
