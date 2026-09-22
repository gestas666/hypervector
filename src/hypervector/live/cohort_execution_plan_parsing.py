"""Strict scalar parsers shared by execution contracts."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.live.cohort_execution_plan_validation import CohortExecutionPlanError


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise CohortExecutionPlanError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CohortExecutionPlanError(f"{label} must be non-empty text")
    return value.strip()


def _positive(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise CohortExecutionPlanError(f"{label} must be positive")
    return number


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _number(value, label)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CohortExecutionPlanError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise CohortExecutionPlanError(f"{label} must be finite")
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CohortExecutionPlanError(f"{label} must be an integer")
    return value


def _integer_field(row: Mapping[str, object], key: str) -> int:
    return _integer(row.get(key), key)


def _optional_integer(value: object, label: str) -> int | None:
    return None if value is None else _integer(value, label)


def _optional_integer_field(row: Mapping[str, object], key: str) -> int | None:
    return _optional_integer(row.get(key), key)


def _positive_integer(value: object, label: str) -> int:
    number = _integer(value, label)
    if number <= 0:
        raise CohortExecutionPlanError(f"{label} must be positive")
    return number


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CohortExecutionPlanError(f"{label} must be boolean")
    return value


