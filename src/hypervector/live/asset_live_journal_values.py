"""Strict value helpers for live lifecycle journal attribution."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import cast

Record = Mapping[str, object]


def payload_value(record: Record | None, key: str) -> object:
    """Return a payload field or None when its record is absent."""
    return None if record is None else payload(record).get(key)


def payload(record: Record | None) -> Mapping[str, object]:
    """Return one validated ledger payload."""
    if record is None:
        return {}
    value = record.get("payload")
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("live ledger payload must be an object")
    return cast(dict[str, object], value)


def sequence(record: Record) -> int:
    """Return one required ledger sequence."""
    return required_int(record.get("sequence"), "sequence")


def required_direction(value: object) -> str:
    """Return a supported long or short lifecycle direction."""
    if value not in {"long", "short"}:
        raise ValueError("live lifecycle direction must be long or short")
    return cast(str, value)


def required_positive_int(value: object, label: str) -> int:
    """Return one required positive integer."""
    result = positive_int(value)
    if result is None:
        raise ValueError(f"live journal {label} must be a positive integer")
    return result


def positive_int(value: object) -> int | None:
    """Return a positive integer when valid."""
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


def required_int(value: object, label: str) -> int:
    """Return one required integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"live journal {label} must be an integer")
    return value


def required_float(value: object) -> float:
    """Return one required finite number."""
    result = optional_float(value)
    if result is None:
        raise ValueError("live journal numeric field must be finite")
    return result


def optional_float(value: object) -> float | None:
    """Return a finite number when valid."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def optional_positive_float(value: object) -> float | None:
    """Return a finite positive number when valid."""
    result = optional_float(value)
    return result if result is not None and result > 0.0 else None
