"""Strict value readers for provider episode research evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

Record = Mapping[str, object]


def mapping(value: object, label: str) -> Record:
    """Return a required mapping or fail on malformed evidence."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def optional_mapping(value: object, label: str) -> Record:
    """Return an optional mapping without inventing absent values."""
    if value is None:
        return {}
    return mapping(value, label)


def sequence(value: object, label: str) -> Sequence[object]:
    """Return a required non-text sequence."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an array")
    return value


def text(value: object, label: str) -> str:
    """Return required non-empty text."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def optional_text(value: object, label: str) -> str | None:
    """Return optional non-empty text."""
    if value is None:
        return None
    return text(value, label)


def choice(value: object, allowed: frozenset[str], label: str) -> str:
    """Return a normalized value from an explicit categorical domain."""
    selected = text(value, label).lower()
    if selected not in allowed:
        raise ValueError(f"unsupported {label}: {selected}")
    return selected


def boolean(value: object, label: str) -> bool:
    """Return a required boolean without numeric coercion."""
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def integer(value: object, label: str) -> int:
    """Return a required non-negative integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def optional_integer(value: object, label: str) -> int | None:
    """Return an optional non-negative integer."""
    if value is None:
        return None
    return integer(value, label)


def number(value: object, label: str) -> float:
    """Return a required finite number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def optional_number(value: object) -> float | None:
    """Return optional finite numeric telemetry."""
    if value is None:
        return None
    return number(value, "optional numeric telemetry")


def row_text(row: Mapping[str, object], field: str) -> str:
    """Read one required text field from a report row."""
    return text(row.get(field), field.replace("_", " "))


def row_number(row: Mapping[str, object], field: str) -> float:
    """Read one required numeric field from a report row."""
    return number(row.get(field), field.replace("_", " "))


def cadence_ms(timeframe: str) -> int:
    """Translate the frozen HIP-3 provider clock to milliseconds."""
    if timeframe != "15m":
        raise ValueError(f"unsupported HIP-3 source timeframe: {timeframe}")
    return 15 * 60 * 1_000


def technical_boundary(evaluation: Record) -> bool:
    """Identify an explicit provider warmup continuity boundary."""
    readiness = mapping(evaluation.get("readiness"), "provider readiness")
    blockers = sequence(readiness.get("blockers"), "provider blockers")
    return "indicator_warmup" in blockers
