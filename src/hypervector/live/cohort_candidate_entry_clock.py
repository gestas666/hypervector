"""Incremental accepted-entry recovery for independently staged providers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path


class CandidateEntryClockStateError(RuntimeError):
    """Raised when candidate cadence cannot be recovered without guessing."""


class AcceptedEntryClock:
    """Recover the latest accepted entry for one exact strategy-symbol pair."""

    def __init__(self, path: Path | None, *, strategy_id: str, symbol: str) -> None:
        """Bind an append-only ledger and consume its current complete prefix."""
        if not strategy_id.strip() or not symbol.strip():
            raise ValueError("candidate clock identity must be non-empty")
        self._path = path
        self._strategy_id = strategy_id
        self._symbol = symbol
        self._offset = 0
        self._line_number = 0
        self.latest_ms: int | None = None
        self.refresh()

    def refresh(self) -> None:
        """Consume complete appended rows and update the accepted-entry time."""
        if self._path is None or not self._path.exists():
            return
        size = self._path.stat().st_size
        if size < self._offset:
            raise CandidateEntryClockStateError(
                "candidate recovery ledger was truncated"
            )
        with self._path.open("rb") as handle:
            handle.seek(self._offset)
            encoded = handle.read()
        if not encoded:
            return
        if not encoded.endswith(b"\n"):
            raise CandidateEntryClockStateError(
                "candidate recovery ledger has an incomplete final row"
            )
        try:
            rows = encoded.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise CandidateEntryClockStateError(
                "candidate recovery ledger is not valid UTF-8"
            ) from exc
        for raw in rows:
            self._line_number += 1
            row = _ledger_row(raw, self._line_number)
            if _contains_entry(
                row,
                strategy_id=self._strategy_id,
                symbol=self._symbol,
            ):
                observed_ms = _observed_time_ms(row, self._line_number)
                self.latest_ms = max(observed_ms, self.latest_ms or 0)
        self._offset += len(encoded)


def _ledger_row(raw: str, line_number: int) -> Mapping[str, object]:
    try:
        value: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CandidateEntryClockStateError(
            f"candidate recovery ledger line {line_number} is invalid JSON"
        ) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CandidateEntryClockStateError(
            f"candidate recovery ledger line {line_number} must be an object"
        )
    return value


def _contains_entry(
    row: Mapping[str, object],
    *,
    strategy_id: str,
    symbol: str,
) -> bool:
    if row.get("event_type") != "intent_routing":
        return False
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise CandidateEntryClockStateError(
            "candidate intent_routing payload must be an object"
        )
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise CandidateEntryClockStateError(
            "candidate intent_routing actions must be a list"
        )
    for action in actions:
        if not isinstance(action, dict):
            raise CandidateEntryClockStateError(
                "candidate intent_routing action must be an object"
            )
        if (
            action.get("action") == "enter"
            and action.get("strategy_id") == strategy_id
            and action.get("symbol") == symbol
        ):
            return True
    return False


def _observed_time_ms(row: Mapping[str, object], line_number: int) -> int:
    raw = row.get("observed_at_utc")
    if not isinstance(raw, str):
        raise CandidateEntryClockStateError(
            f"candidate recovery ledger line {line_number} lacks observed_at_utc"
        )
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateEntryClockStateError(
            f"candidate recovery ledger line {line_number} has invalid observed_at_utc"
        ) from exc
    if observed.tzinfo is None:
        raise CandidateEntryClockStateError(
            f"candidate recovery ledger line {line_number} time must be timezone-aware"
        )
    return int(observed.astimezone(timezone.utc).timestamp() * 1_000)
