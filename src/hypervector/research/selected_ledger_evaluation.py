"""Bounded exact-event evidence from an append-only decision ledger."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

Record = Mapping[str, object]


@dataclass(frozen=True)
class SelectedLedgerEvaluation:
    """One exact routing row plus point-in-time source evidence."""

    path: Path
    row: dict[str, object]
    evaluation: dict[str, object]
    evidence: dict[str, object]


def read_exact_provider_evaluation(
    path: Path,
    *,
    run_id: str,
    provider_id: str,
    symbol: str,
    decision_time_ms: int,
) -> SelectedLedgerEvaluation:
    """Stream one stable prefix and select exactly one provider evaluation."""
    _validate_target(path, run_id, provider_id, symbol, decision_time_ms)
    source = path.stat()
    observed_bytes = source.st_size
    selected: tuple[int, bytes, dict[str, object], dict[str, object]] | None = None
    stable_bytes = 0
    with path.open("rb") as handle:
        while handle.tell() < observed_bytes:
            offset = handle.tell()
            raw = handle.readline(observed_bytes - offset)
            if not raw.endswith(b"\n"):
                break
            stable_bytes = handle.tell()
            match = _matching_row(raw, run_id, provider_id, symbol, decision_time_ms)
            if match is None:
                continue
            if selected is not None:
                raise ValueError("duplicate exact provider evaluation")
            selected = (offset, raw, *match)
    if selected is None:
        raise ValueError("exact provider evaluation was not found")
    return _selection(
        path,
        source.st_dev,
        source.st_ino,
        observed_bytes,
        stable_bytes,
        selected,
    )


def require_selected_evaluation_unchanged(
    selected: SelectedLedgerEvaluation,
) -> None:
    """Reject truncation, replacement, or mutation of the selected event."""
    current = selected.path.stat()
    evidence = selected.evidence
    if (
        current.st_dev != evidence["source_device"]
        or current.st_ino != evidence["source_inode"]
        or current.st_size < evidence["source_bytes_observed"]
    ):
        raise RuntimeError("selected ledger source identity changed")
    with selected.path.open("rb") as handle:
        handle.seek(_integer(evidence, "event_offset"))
        raw = handle.read(_integer(evidence, "event_bytes"))
    if sha256(raw).hexdigest() != evidence["event_sha256"]:
        raise RuntimeError("selected ledger event changed")


def _validate_target(
    path: Path,
    run_id: str,
    provider_id: str,
    symbol: str,
    decision_time_ms: int,
) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"decision ledger does not exist: {path}")
    if any(not value.strip() for value in (run_id, provider_id, symbol)):
        raise ValueError("selected ledger identity requires nonempty text")
    if isinstance(decision_time_ms, bool) or decision_time_ms < 0:
        raise ValueError("selected ledger decision time must be nonnegative")


def _matching_row(
    raw: bytes,
    run_id: str,
    provider_id: str,
    symbol: str,
    decision_time_ms: int,
) -> tuple[dict[str, object], dict[str, object]] | None:
    probes = (
        b'"event_type":"intent_routing"',
        provider_id.encode(),
        str(decision_time_ms).encode(),
    )
    if any(probe not in raw for probe in probes):
        return None
    value: object = json.loads(raw)
    row = _object(value, "decision ledger row")
    if row.get("event_type") != "intent_routing" or row.get("run_id") != run_id:
        return None
    payload = _object(row.get("payload"), "intent-routing payload")
    evaluations = payload.get("evaluations")
    if not isinstance(evaluations, list):
        raise ValueError("intent-routing evaluations must be a list")
    matches = [
        _object(item, "provider evaluation")
        for item in evaluations
        if _is_target(item, provider_id, symbol, decision_time_ms)
    ]
    if len(matches) > 1:
        raise ValueError("duplicate exact provider evaluation within routing row")
    return (dict(row), dict(matches[0])) if matches else None


def _is_target(
    value: object,
    provider_id: str,
    symbol: str,
    decision_time_ms: int,
) -> bool:
    return isinstance(value, Mapping) and (
        value.get("strategy_id"),
        value.get("symbol"),
        value.get("decision_time_ms"),
    ) == (provider_id, symbol, decision_time_ms)


def _selection(
    path: Path,
    device: int,
    inode: int,
    observed: int,
    stable: int,
    selected: tuple[int, bytes, dict[str, object], dict[str, object]],
) -> SelectedLedgerEvaluation:
    offset, raw, row, evaluation = selected
    evidence: dict[str, object] = {
        "path": str(path.resolve()),
        "source_device": device,
        "source_inode": inode,
        "source_bytes_observed": observed,
        "stable_bytes": stable,
        "dropped_tail_bytes": observed - stable,
        "incomplete_tail_dropped": stable < observed,
        "event_offset": offset,
        "event_bytes": len(raw),
        "event_sha256": sha256(raw).hexdigest(),
    }
    return SelectedLedgerEvaluation(path.resolve(), row, evaluation, evidence)


def _object(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: Record, key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise RuntimeError(f"selected ledger evidence has invalid {key}")
    return result
