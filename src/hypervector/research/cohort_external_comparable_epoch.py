"""Source-comparable decision epochs for external candidate monitoring."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    require_jsonl_prefix_unchanged,
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class ComparableDecisionEpoch:
    """Validated epoch counts and the consumed append-only prefix evidence."""

    status: dict[str, object]
    evidence: dict[str, object]


def load_comparable_decision_epoch(
    catalog_path: Path,
    record: Record,
    *,
    symbol: str,
    profile_id: str,
    provider_id: str,
    observed_at_ms: int,
) -> ComparableDecisionEpoch | None:
    """Load one optional source-comparable decision epoch from its journal."""
    source_value = record.get("comparable_decision_epoch")
    if source_value is None:
        return None
    source = _mapping(source_value, "comparable decision epoch")
    start_ms = _positive_integer(source.get("decision_start_ms"), "epoch start")
    path = _resolve(catalog_path, source.get("journal_path"))
    rows, evidence = read_jsonl_prefix(path, "comparable decision journal")
    bounded = _bounded_decisions(
        rows, start_ms, observed_at_ms, symbol, profile_id, provider_id
    )
    require_jsonl_prefix_unchanged(path, evidence, "comparable decision journal")
    return ComparableDecisionEpoch(_status(start_ms, bounded), evidence)


def _bounded_decisions(
    rows: tuple[dict[str, object], ...],
    start_ms: int,
    observed_at_ms: int,
    symbol: str,
    profile_id: str,
    provider_id: str,
) -> tuple[tuple[int, bool, str | None], ...]:
    bounded: list[tuple[int, bool, str | None]] = []
    for row in rows:
        decision = _mapping(row.get("decision"), "comparable decision")
        decision_ms = _nonnegative_integer(
            decision.get("decision_time_ms"), "decision time"
        )
        if decision_ms < start_ms:
            continue
        if decision_ms > observed_at_ms:
            raise ValueError("comparable decision journal contains future evidence")
        _require_identity(row, decision, symbol, profile_id, provider_id)
        eligible = decision.get("eligible")
        if not isinstance(eligible, bool):
            raise ValueError("comparable decision eligibility must be boolean")
        side = _side(decision.get("side"), eligible)
        bounded.append((decision_ms, eligible, side))
    times = [row[0] for row in bounded]
    if len(times) != len(set(times)) or times != sorted(times):
        raise ValueError("comparable decision times must be ordered and unique")
    return tuple(bounded)


def _require_identity(
    row: Record,
    decision: Record,
    symbol: str,
    profile_id: str,
    provider_id: str,
) -> None:
    expected_row = {
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    expected_decision = {
        "symbol": symbol,
        "profile_id": profile_id,
        "provider_id": provider_id,
        "prospective": True,
        "execution_authority": "none",
    }
    if any(row.get(key) != value for key, value in expected_row.items()):
        raise ValueError("comparable decision row contract is invalid")
    if any(decision.get(key) != value for key, value in expected_decision.items()):
        raise ValueError("comparable decision identity is invalid")


def _status(
    start_ms: int, rows: tuple[tuple[int, bool, str | None], ...]
) -> dict[str, object]:
    eligible = [row for row in rows if row[1]]
    return {
        "decision_start_ms": start_ms,
        "decision_rows": len(rows),
        "eligible_decisions": len(eligible),
        "long_decisions": sum(row[2] == "long" for row in eligible),
        "short_decisions": sum(row[2] == "short" for row in eligible),
        "non_action_decisions": len(rows) - len(eligible),
        "first_decision_time_ms": None if not rows else rows[0][0],
        "last_decision_time_ms": None if not rows else rows[-1][0],
        "state": _state(rows, eligible),
    }


def _state(
    rows: tuple[tuple[int, bool, str | None], ...],
    eligible: list[tuple[int, bool, str | None]],
) -> str:
    if not rows:
        return "waiting_observed_decision"
    return "eligible_onset_observed" if eligible else "waiting_eligible_onset"


def _side(value: object, eligible: bool) -> str | None:
    if not eligible and value is None:
        return None
    if eligible and value in {"long", "short"}:
        return str(value)
    raise ValueError("comparable decision side does not match eligibility")


def _resolve(catalog_path: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("comparable decision journal path must be non-empty text")
    path = Path(value.strip())
    return path if path.is_absolute() else (catalog_path.parent / path).resolve()


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_integer(value: object, label: str) -> int:
    number = _nonnegative_integer(value, label)
    if number == 0:
        raise ValueError(f"{label} must be positive")
    return number
