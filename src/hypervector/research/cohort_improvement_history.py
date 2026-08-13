"""Hash-chained material-change history for cohort improvement research."""

from __future__ import annotations

from collections.abc import Mapping
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import TextIO

Record = Mapping[str, object]


def append_material_report(path: Path, report: Record) -> bool:
    """Append one new report state; return false when material state is unchanged."""
    material_hash = _digest_text(
        report.get("material_state_sha256"), "material state hash"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            prior = _read_events(stream)
            if prior and prior[-1]["material_state_sha256"] == material_hash:
                return False
            event = _event(report, material_hash, prior)
            stream.seek(0, 2)
            stream.write(
                json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
            return True
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _read_events(stream: TextIO) -> list[dict[str, object]]:
    stream.seek(0)
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(stream, 1):
        if not line.strip():
            raise ValueError(f"history event {line_number} is blank")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"history event {line_number} is invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"history event {line_number} must be an object")
        try:
            _validate_event(value, line_number, rows)
        except ValueError as exc:
            raise ValueError(f"history event {line_number} is invalid: {exc}") from exc
        rows.append(value)
    return rows


def _validate_event(
    event: dict[str, object],
    line_number: int,
    prior: list[dict[str, object]],
) -> None:
    if event.get("sequence") != line_number:
        raise ValueError(f"history event {line_number} sequence is invalid")
    previous = prior[-1]["event_sha256"] if prior else None
    if event.get("previous_event_sha256") != previous:
        raise ValueError(f"history event {line_number} chain is invalid")
    _digest_text(event.get("material_state_sha256"), "material state hash")
    expected = _event_hash(event)
    if event.get("event_sha256") != expected:
        raise ValueError(f"history event {line_number} hash is invalid")


def _event(
    report: Record,
    material_hash: str,
    prior: list[dict[str, object]],
) -> dict[str, object]:
    event = {
        "schema_version": 1,
        "sequence": len(prior) + 1,
        "recorded_at_utc": _text(report.get("generated_at_utc"), "report time"),
        "previous_event_sha256": prior[-1]["event_sha256"] if prior else None,
        "material_state_sha256": material_hash,
        "source": _mapping(report.get("source"), "report source"),
        "operational_assessment": _mapping(
            report.get("operational_assessment"), "operational assessment"
        ),
        "highest_value_next_investigation": report.get(
            "highest_value_next_investigation"
        ),
        "hypothesis_ledger": _list(
            report.get("hypothesis_ledger"), "hypothesis ledger"
        ),
        "change_proposals": _list(report.get("change_proposals"), "change proposals"),
        "contract": _mapping(report.get("contract"), "report contract"),
    }
    event["event_sha256"] = _event_hash(event)
    return event


def _event_hash(event: Record) -> str:
    payload = {key: value for key, value in event.items() if key != "event_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _digest_text(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{label} must be lowercase SHA-256")
    return text


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return list(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
