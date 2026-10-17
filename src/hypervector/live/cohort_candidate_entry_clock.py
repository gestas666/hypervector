"""Incremental accepted-entry recovery for independently staged providers.

Every clock bound to the same ledger file shares one incremental, validated
scan. The scan reads each appended row once and records, for every
(strategy, symbol) pair it sees entered, the latest accepted time and the
first failure that a clock for that pair would have raised. A clock then
publishes exactly what an independent scan of the same bytes would publish,
and raises exactly the first failure such a scan would raise, without the
ledger being parsed again for each provider.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import weakref
import zlib


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
        self._pair = (strategy_id, symbol)
        self._scan: _SharedLedgerScan | None = None
        self._offset = 0
        self._line_number = 0
        self.latest_ms: int | None = None
        self.refresh()

    def refresh(self) -> None:
        """Consume complete appended rows and update the accepted-entry time."""
        if self._path is None or not self._path.exists():
            return
        if self._scan is None:
            self._scan = _bind_shared_scan(self._path)
        scan = self._scan
        with scan.lock:
            try:
                scan.advance()
            except Exception as exc:  # noqa: BLE001 - re-raised below unchanged
                fatal: Exception | None = exc
            else:
                fatal = None
            failure = scan.first_failure(self._pair)
            if failure is None and fatal is None:
                self._offset = scan.offset
                self._line_number = scan.line_number
                self.latest_ms = scan.latest.get(self._pair)
                return
        if failure is None:
            raise fatal  # type: ignore[misc]
        # Every recorded failure precedes the row a fatal error stopped at, so
        # an independent scan for this pair would have raised it first.
        raise CandidateEntryClockStateError(failure.message) from failure.cause


_ROUTING_MARKER = b"intent_routing"
_ESCAPE = b"\\"
_CRC_CHUNK = 1 << 20
_BOM = "\ufeff"
# Validates JSON exactly as ``json.loads`` does while leaving float literals as
# text: the number grammar is checked by the scanner before ``parse_float`` is
# called, and default float conversion cannot fail, so acceptance is unchanged.
_OBJECT_VALIDATOR = json.JSONDecoder(parse_float=str)
_SCANS: weakref.WeakValueDictionary[tuple[str, int, int], _SharedLedgerScan] = (
    weakref.WeakValueDictionary()
)
_SCANS_LOCK = threading.Lock()


@dataclass(frozen=True)
class _Failure:
    """The first error an independent scan for some pairs would have raised."""

    line_number: int
    message: str
    cause: BaseException | None = None
    # For a row-wide failure: the pairs an independent scan accepts at this
    # row instead, because their entry precedes the malformed action.
    exempt: frozenset[tuple[str, str]] = frozenset()


class _SharedLedgerScan:
    """One incremental validated pass over a ledger, shared by its clocks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.offset = 0
        self.line_number = 0
        self.latest: dict[tuple[str, str], int] = {}
        self._pair_failures: dict[tuple[str, str], _Failure] = {}
        self._row_failures: list[_Failure] = []
        self._crc = 0

    def first_failure(self, pair: tuple[str, str]) -> _Failure | None:
        """Return the earliest committed failure that applies to ``pair``."""
        failure = self._pair_failures.get(pair)
        for row in self._row_failures:
            if failure is not None and row.line_number >= failure.line_number:
                break
            if pair not in row.exempt:
                return row
        return failure

    def prefix_matches(self, size: int) -> bool:
        """Report whether the file still holds the consumed bytes (CRC-32).

        A clock bound later relies on rows this scan already validated, so it
        joins only while those bytes are unchanged; otherwise it starts over.
        """
        if self.offset == 0:
            return True
        if size < self.offset:
            return False
        crc = 0
        with self.path.open("rb") as handle:
            remaining = self.offset
            while remaining:
                chunk = handle.read(min(remaining, _CRC_CHUNK))
                if not chunk:
                    return False
                crc = zlib.crc32(chunk, crc)
                remaining -= len(chunk)
        return crc == self._crc

    def advance(self) -> None:
        """Consume complete appended rows, committing each validated row.

        A file shorter than the consumed boundary is refused for every clock
        bound to this scan, including one that had not yet consumed as far.
        """
        size = self.path.stat().st_size
        if size < self.offset:
            raise CandidateEntryClockStateError("candidate recovery ledger was truncated")
        if size == self.offset:
            return
        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            remaining = size - self.offset
            while remaining:
                encoded = handle.readline(remaining)
                if not encoded:
                    raise CandidateEntryClockStateError(
                        "candidate recovery ledger was truncated"
                    )
                self._consume(encoded, self.line_number + 1)
                self._crc = zlib.crc32(encoded, self._crc)
                self.offset += len(encoded)
                self.line_number += 1
                remaining -= len(encoded)

    def _consume(self, encoded: bytes, line_number: int) -> None:
        raw = _complete_utf8_row(encoded)
        # Without the literal marker or any escape, no decoded string can equal
        # "intent_routing", so the row can only need JSON object validation.
        if _ROUTING_MARKER not in encoded and _ESCAPE not in encoded:
            _require_json_object(raw, line_number)
            return
        row = _ledger_row(raw, line_number)
        if row.get("event_type") != "intent_routing":
            return
        matched, bad_action = _entered_pairs(row)
        if bad_action:
            self._row_failures.append(
                _Failure(
                    line_number,
                    "candidate intent_routing action must be an object",
                    exempt=frozenset(matched),
                )
            )
        if not matched:
            return
        try:
            observed_ms = _observed_time_ms(row, line_number)
        except CandidateEntryClockStateError as exc:
            failure = _Failure(line_number, str(exc), exc.__cause__)
            for pair in matched:
                self._pair_failures.setdefault(pair, failure)
            return
        for pair in matched:
            self.latest[pair] = max(observed_ms, self.latest.get(pair) or 0)


def _bind_shared_scan(path: Path) -> _SharedLedgerScan:
    """Return the live scan of this exact file, or start a fresh one."""
    status = path.stat()
    absolute = os.path.abspath(path)
    key = (absolute, status.st_dev, status.st_ino)
    with _SCANS_LOCK:
        scan = _SCANS.get(key)
        if scan is not None:
            with scan.lock:
                reusable = scan.prefix_matches(status.st_size)
            if reusable:
                return scan
        # A shrunk or rewritten file starts a fresh scan for new clocks, exactly
        # as a fresh clock would; clocks already bound keep the old scan, which
        # refuses the truncation. The bound path is absolute, so every clock
        # reads the file its identity was taken from.
        scan = _SharedLedgerScan(Path(absolute))
        _SCANS[key] = scan
        return scan


def _complete_utf8_row(encoded: bytes) -> str:
    if not encoded.endswith(b"\n"):
        raise CandidateEntryClockStateError("candidate recovery ledger has an incomplete final row")
    try:
        return encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CandidateEntryClockStateError("candidate recovery ledger is not valid UTF-8") from exc


def _require_json_object(raw: str, line_number: int) -> None:
    """Apply the ``_ledger_row`` contract without materializing float values."""
    try:
        if raw.startswith(_BOM):
            # ``json.loads`` refuses a byte-order mark before decoding.
            raise json.JSONDecodeError(
                "Unexpected UTF-8 BOM (decode using utf-8-sig)", raw, 0
            )
        value: object = _OBJECT_VALIDATOR.decode(raw)
    except json.JSONDecodeError as exc:
        raise CandidateEntryClockStateError(
            f"candidate recovery ledger line {line_number} is invalid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise CandidateEntryClockStateError(
            f"candidate recovery ledger line {line_number} must be an object"
        )


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


def _entered_pairs(row: Mapping[str, object]) -> tuple[set[tuple[str, str]], bool]:
    """Return pairs an independent clock accepts here, and any malformed action.

    A clock stops at its first matching action, so a pair entered before a
    malformed action is accepted while every other pair fails at this row.
    """
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
    matched: set[tuple[str, str]] = set()
    for action in actions:
        if not isinstance(action, dict):
            return matched, True
        strategy_id = action.get("strategy_id")
        symbol = action.get("symbol")
        if (
            action.get("action") == "enter"
            and isinstance(strategy_id, str)
            and isinstance(symbol, str)
        ):
            matched.add((strategy_id, symbol))
    return matched, False


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
    try:
        return int(observed.astimezone(timezone.utc).timestamp() * 1_000)
    except (OverflowError, ValueError) as exc:
        # An offset time beyond the representable UTC range is refused for the
        # matched pairs only; it must not become a row-wide shared-scan error.
        raise CandidateEntryClockStateError(
            f"candidate recovery ledger line {line_number} has invalid observed_at_utc"
        ) from exc
