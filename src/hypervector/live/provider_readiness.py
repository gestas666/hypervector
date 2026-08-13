"""Backend-owned strategy setup readiness for read-only operator telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from types import MappingProxyType

ReadinessMetric = str | int | float | bool | None


@dataclass(frozen=True)
class SignalReadiness:
    """Measured setup prerequisites and blockers without execution authority."""

    side: str | None
    conditions_met: int
    conditions_required: int
    blockers: tuple[str, ...]
    indicators: tuple[str, ...]
    metrics: Mapping[str, ReadinessMetric] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject malformed or success-shaped readiness telemetry."""
        if self.side not in {None, "long", "short"}:
            raise ValueError("readiness side must be long, short, or None")
        values = (self.conditions_met, self.conditions_required)
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in values
        ):
            raise ValueError("readiness condition counts must be integers")
        if self.conditions_required < 1:
            raise ValueError("conditions_required must be positive")
        if not 0 <= self.conditions_met <= self.conditions_required:
            raise ValueError("conditions_met must be within the required count")
        _validate_text(self.blockers, "blockers")
        _validate_text(self.indicators, "indicators", require_values=True)
        object.__setattr__(self, "metrics", _validated_metrics(self.metrics))

    @property
    def fraction(self) -> float:
        """Return the measured prerequisite fraction, not a win probability."""
        value = self.conditions_met / self.conditions_required
        if not math.isfinite(value):
            raise ValueError("readiness fraction must be finite")
        return value

    def as_payload(self) -> dict[str, object]:
        """Return the stable JSON-safe backend telemetry contract."""
        return {
            "side": self.side,
            "conditions_met": self.conditions_met,
            "conditions_required": self.conditions_required,
            "readiness_fraction": self.fraction,
            "blockers": list(self.blockers),
            "indicators": list(self.indicators),
            "metrics": dict(self.metrics),
        }


def _validate_text(
    values: tuple[str, ...],
    label: str,
    *,
    require_values: bool = False,
) -> None:
    if require_values and not values:
        raise ValueError(f"readiness {label} must not be empty")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"readiness {label} must contain non-empty text")


def _validated_metrics(
    values: Mapping[str, ReadinessMetric],
) -> Mapping[str, ReadinessMetric]:
    output: dict[str, ReadinessMetric] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("readiness metric names must be non-empty text")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(f"readiness metric {key} has an unsupported value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(float(value)):
                raise ValueError(f"readiness metric {key} must be finite")
        output[key.strip()] = value
    return MappingProxyType(dict(sorted(output.items())))
