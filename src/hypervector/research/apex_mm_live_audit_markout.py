"""Configured-horizon validation for Apex MM fill markouts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import median


def audit_markout_horizons(
    identity: Mapping[str, object],
    markouts: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], list[str]]:
    """Summarize actual horizons and reject evidence outside its contract."""
    requested, maximum = _contract(identity)
    observed = [_optional_horizon(payload) for payload in markouts]
    values = [value for value in observed if value is not None]
    gaps: list[str] = []
    if markouts and (requested is None or maximum is None):
        gaps.append("markout_horizon_contract_missing")
    if len(values) < len(markouts):
        gaps.append("markout_horizon_missing")
    if requested is not None and any(value < requested for value in values):
        gaps.append("markout_before_requested_horizon")
    if maximum is not None and any(value > maximum for value in values):
        gaps.append("markout_horizon_exceeded_tolerance")
    return _summary(requested, maximum, values), gaps


def _contract(identity: Mapping[str, object]) -> tuple[int | None, int | None]:
    execution = identity.get("execution")
    if not isinstance(execution, Mapping):
        return None, None
    requested = _positive_integer(execution.get("markout_horizon_ms"))
    tolerance = _nonnegative_integer(execution.get("maximum_book_age_ms"))
    maximum = (
        requested + tolerance
        if requested is not None and tolerance is not None
        else None
    )
    return requested, maximum


def _optional_horizon(payload: Mapping[str, object]) -> int | None:
    value = payload.get("horizon_ms")
    return _nonnegative_integer(value)


def _summary(
    requested: int | None,
    maximum: int | None,
    values: Sequence[int],
) -> dict[str, object]:
    return {
        "requested": requested,
        "maximum_accepted": maximum,
        "count": len(values),
        "minimum": float(min(values)) if values else None,
        "median": float(median(values)) if values else None,
        "maximum": float(max(values)) if values else None,
        "mean": sum(values) / len(values) if values else None,
        "within_tolerance": sum(
            requested is not None
            and maximum is not None
            and requested <= value <= maximum
            for value in values
        ),
    }


def _positive_integer(value: object) -> int | None:
    observed = _nonnegative_integer(value)
    return observed if observed is not None and observed > 0 else None


def _nonnegative_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
