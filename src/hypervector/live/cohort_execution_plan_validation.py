"""Shared validation primitives for provider execution plans."""

from __future__ import annotations

import math


class CohortExecutionPlanError(ValueError):
    """A provider execution contract is incomplete or internally inconsistent."""


def validate_profit_lock_contract(
    policy: str,
    activation_bps: float | None,
    floor_bps: float | None,
    giveback_bps: float | None,
) -> None:
    """Reject incomplete or internally inconsistent profit-lock parameters."""
    values = (activation_bps, floor_bps, giveback_bps)
    supported = {
        "none",
        "completed_bar_trailing",
        "btc_hulk_delayed_component_floor_v1",
        "btc_hulk_delayed_component_exit_v2",
    }
    if policy not in supported:
        raise CohortExecutionPlanError("unsupported profit lock policy")
    if policy in {
        "btc_hulk_delayed_component_floor_v1",
        "btc_hulk_delayed_component_exit_v2",
    }:
        if any(value is not None for value in values):
            raise CohortExecutionPlanError(
                "BTC Hulk delayed component floor cannot define fixed-bps parameters"
            )
        return
    if policy == "none":
        if any(value is not None for value in values):
            raise CohortExecutionPlanError(
                "disabled profit lock cannot define lock parameters"
            )
        return
    if any(value is None for value in values):
        raise CohortExecutionPlanError(
            "completed-bar profit lock requires activation, floor, and giveback"
        )
    activation = _positive(activation_bps, "profit_lock_activation_bps")
    floor = _positive(floor_bps, "profit_lock_floor_bps")
    _positive(giveback_bps, "profit_lock_giveback_bps")
    if floor > activation:
        raise CohortExecutionPlanError(
            "profit lock floor cannot exceed activation threshold"
        )


def _positive(value: float | None, label: str) -> float:
    if value is None or not math.isfinite(value) or value <= 0.0:
        raise CohortExecutionPlanError(f"{label} must be positive and finite")
    return value
