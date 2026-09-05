"""Typed validation helpers for exact-route lifecycle evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import math

Record = Mapping[str, object]

_SIDES = frozenset(("long", "short"))
REPORT_CONTRACT: dict[str, object] = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_live_change": False,
    "runtime_strategy_changed": False,
    "orders_or_fills_assumed": False,
    "promotion_authority": "none",
}


def mapping(value: object, label: str) -> Record:
    """Require one object mapping."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def records(value: object, label: str) -> list[Record]:
    """Require an array containing only object mappings."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an array")
    if any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} must contain objects")
    return [mapping(row, label) for row in value]


def text_sequence(value: object, label: str) -> list[str]:
    """Require a unique array of non-empty strings."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an array")
    output = [text(item, label) for item in value]
    if len(output) != len(set(output)):
        raise ValueError(f"{label} must be unique")
    return output


def timestamp(value: object, label: str) -> datetime:
    """Parse one timezone-aware timestamp as UTC."""
    source = text(value, label).replace("Z", "+00:00")
    result = datetime.fromisoformat(source)
    if result.tzinfo is None:
        raise ValueError(f"{label} needs a timezone")
    return result.astimezone(UTC)


def side(value: object) -> str:
    """Require a canonical long or short side."""
    result = text(value, "lifecycle side")
    if result not in _SIDES:
        raise ValueError("lifecycle side must be long or short")
    return result


def text(value: object, label: str) -> str:
    """Require non-empty text."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def count(value: object, label: str) -> int:
    """Require a nonnegative integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def number(value: object, label: str) -> float:
    """Require a finite numeric value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def evidence_mapping(row: Record, field: str, missing: list[str]) -> Record:
    """Return required nested evidence or record one missing field."""
    value = row.get(field)
    if value is None:
        missing.append(field)
        return {}
    return mapping(value, field.replace("_", " "))


def nested_mapping(row: Record, field: str, label: str, missing: list[str]) -> Record:
    """Return required nested evidence with a readable missing label."""
    value = row.get(field)
    if value is None:
        missing.append(label.replace(" ", "_"))
        return {}
    return mapping(value, label)


def number_field(
    row: Record, field: str, missing: list[str], *, prefix: str = ""
) -> float | None:
    """Read a required numeric field while preserving incompleteness."""
    path = f"{prefix}.{field}" if prefix else field
    if row.get(field) is None:
        missing.append(path)
        return None
    return number(row.get(field), path)


def integer_field(
    row: Record, field: str, missing: list[str], *, prefix: str = ""
) -> int | None:
    """Read a required integer field while preserving incompleteness."""
    path = f"{prefix}.{field}" if prefix else field
    if row.get(field) is None:
        missing.append(path)
        return None
    return count(row.get(field), path)


def text_field(row: Record, field: str, missing: list[str]) -> str | None:
    """Read required text while preserving incompleteness."""
    if row.get(field) is None:
        missing.append(field)
        return None
    return text(row.get(field), field.replace("_", " "))


def boolean_field(row: Record, field: str, missing: list[str]) -> bool | None:
    """Read a required boolean while preserving incompleteness."""
    value = row.get(field)
    if value is None:
        missing.append(field)
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field.replace('_', ' ')} must be boolean")
    return value


def require_unique_lifecycles(rows: Sequence[Record]) -> None:
    """Reject duplicated lifecycle identities."""
    identities = [row.get("lifecycle_id") for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("route lifecycle identities must be unique")


def validate_report_contract(value: object, label: str) -> None:
    """Require a source contract with no execution authority."""
    contract = mapping(value, f"{label} contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    if any(contract.get(field) != target for field, target in expected.items()):
        raise ValueError(f"{label} contract is not report-only")
