"""Immutable contract for report-only Hypervelocity peak observation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

PEAK_OBSERVER_SCHEMA = "hypervelocity_peak_observer_v1"
PEAK_OBSERVER_CANDIDATE_ID = "source_peak_activation7_v1"


@dataclass(frozen=True)
class PeakObserverConfig:
    """Frozen non-executable settings for the +7% source sensitivity."""

    mode: Literal["off", "observe"]
    candidate_id: str
    activation_margin_pct: float
    lock_ratio: float
    minimum_stop_move_fraction: float
    update_cooldown_seconds: float
    sample_interval_seconds: float
    execution_authority: Literal["none"]

    def __post_init__(self) -> None:
        """Reject drift from the predeclared report-only candidate."""
        _expect("mode", self.mode, {"off", "observe"})
        _expect("candidate_id", self.candidate_id, PEAK_OBSERVER_CANDIDATE_ID)
        _expect_number("activation_margin_pct", self.activation_margin_pct, 7.0)
        _expect_number("lock_ratio", self.lock_ratio, 0.55)
        _expect_number(
            "minimum_stop_move_fraction",
            self.minimum_stop_move_fraction,
            0.0005,
        )
        _expect_number(
            "update_cooldown_seconds",
            self.update_cooldown_seconds,
            60.0,
        )
        _expect_number(
            "sample_interval_seconds",
            self.sample_interval_seconds,
            5.0,
        )
        _expect("execution_authority", self.execution_authority, "none")

    def telemetry(self) -> dict[str, object]:
        """Return the complete immutable report-only contract."""
        return {
            "schema": PEAK_OBSERVER_SCHEMA,
            "mode": self.mode,
            "candidate_id": self.candidate_id,
            "activation_margin_pct": self.activation_margin_pct,
            "lock_ratio": self.lock_ratio,
            "minimum_stop_move_fraction": self.minimum_stop_move_fraction,
            "update_cooldown_seconds": self.update_cooldown_seconds,
            "sample_interval_seconds": self.sample_interval_seconds,
            "execution_authority": self.execution_authority,
            "report_only": True,
        }


def _expect(field: str, actual: object, expected: object) -> None:
    if isinstance(expected, set):
        if actual in expected:
            return
    elif actual == expected:
        return
    raise ValueError(f"peak observer {field} must be {expected!r}")


def _expect_number(field: str, actual: float, expected: float) -> None:
    if math.isfinite(actual) and math.isclose(actual, expected, abs_tol=1e-12):
        return
    raise ValueError(f"peak observer {field} must be {expected}")
