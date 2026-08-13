"""Append-only persistence for the SOL no-submit shadow lifecycle."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, cast

from hypervector.research.sol_range_onset_shadow import SolRangeOnsetShadowEngine
from hypervector.research.sol_range_onset_shadow_models import SolShadowConfig


class SolShadowLedger:
    """Durably persist complete state after each mutation batch."""

    def __init__(self, path: Path, config: SolShadowConfig) -> None:
        self._path = path
        self._config = config
        self._sequence = 0

    def restore_engine(self) -> SolRangeOnsetShadowEngine:
        """Restore the last complete state or return a fresh engine."""
        if not self._path.exists():
            return SolRangeOnsetShadowEngine(self._config)
        latest: Mapping[str, object] | None = None
        expected_sequence = 1
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                row = _json_row(raw, line_number)
                _validate_ledger_row(row, expected_sequence, line_number)
                latest = row
                expected_sequence += 1
        self._sequence = expected_sequence - 1
        if latest is None:
            return SolRangeOnsetShadowEngine(self._config)
        return SolRangeOnsetShadowEngine.from_state(
            self._config,
            _mapping(latest.get("state"), "state"),
        )

    def append(
        self,
        records: tuple[dict[str, object], ...],
        engine: SolRangeOnsetShadowEngine,
        *,
        recorded_at_ms: int,
    ) -> None:
        """Append and fsync one mutation batch with its complete state."""
        if not records:
            return
        if isinstance(recorded_at_ms, bool) or recorded_at_ms <= 0:
            raise ValueError("recorded_at_ms must be a positive integer")
        _validate_records(records)
        self._sequence += 1
        row = {
            "schema_version": 1,
            "sequence": self._sequence,
            "recorded_at_ms": recorded_at_ms,
            "execution_authority": "none",
            "submitted": False,
            "place_attempted": False,
            "records": records,
            "state": engine.export_state(),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())


def _json_row(raw: str, line_number: int) -> Mapping[str, object]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid SOL shadow ledger JSON at line {line_number}"
        ) from exc
    return _mapping(value, f"line {line_number}")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"SOL shadow ledger {label} must be an object")
    return cast(dict[str, object], value)


def _validate_ledger_row(
    row: Mapping[str, object],
    expected_sequence: int,
    line_number: int,
) -> None:
    if row.get("schema_version") != 1 or row.get("sequence") != expected_sequence:
        raise ValueError(f"invalid SOL shadow ledger sequence at line {line_number}")
    if row.get("execution_authority") != "none":
        raise ValueError(f"SOL shadow ledger authority changed at line {line_number}")
    if row.get("submitted") is not False or row.get("place_attempted") is not False:
        raise ValueError(
            f"SOL shadow ledger contains a submission at line {line_number}"
        )
    if not isinstance(row.get("records"), list):
        raise ValueError(
            f"SOL shadow ledger records must be a list at line {line_number}"
        )


def _validate_records(records: tuple[dict[str, object], ...]) -> None:
    for record in records:
        if record.get("execution_authority") != "none":
            raise ValueError("SOL shadow record authority must remain none")
        if record.get("submitted") is not False:
            raise ValueError("SOL shadow records cannot report submission")
        if record.get("place_attempted") is not False:
            raise ValueError("SOL shadow records cannot report placement attempts")
