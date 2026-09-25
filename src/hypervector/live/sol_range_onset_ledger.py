"""Append-only authoritative ledger for the SOL mainnet canary."""

from __future__ import annotations

from array import array
import json
import os
from collections.abc import Callable, Collection, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

SOL_LIVE_EVENT_TYPES = frozenset(
    {
        "session_start",
        "effective_mode",
        "configuration_identity",
        "regime_decision",
        "theoretical_quote",
        "order_intent",
        "entry_stop_risk_sizing",
        "cancel_intent",
        "order_acknowledgement",
        "entry_not_filled",
        "entry_not_submitted",
        "entry_reconciliation_failure",
        "fill",
        "stop_order",
        "protective_stop_raised",
        "breakeven_stop_attempt",
        "breakeven_stop_skipped",
        "protective_stop_raise_exhausted",
        "structural_anchor_overrun",
        "target_order",
        "position",
        "fee",
        "funding",
        "funding_reconciliation_window",
        "liquidation_price",
        "close",
        "fault",
        "state_transition",
        "reconciliation",
        "book_observation",
        "strategy_intent",
        "intent_routing",
        "canonical_regime_evaluations",
        "market_candles",
        "startup_candle_inputs",
        "market_books",
        "operator_command",
        "maximum_hold_decision",
        "provider_exit_decision",
        "profit_lock_decision",
        "adaptive_exit_observation",
        "cohort_snapshot",
        "heartbeat",
        "runtime_fault",
        "runtime_stopped",
    }
)
_SECRET_KEY_FRAGMENTS = ("private_key", "api_key", "secret", "mnemonic")
# Envelope code for a row whose event type or fingerprint is not hashable JSON.
_UNKNOWN_ENVELOPE = 0
LedgerExecutionMode = Literal["live", "observe"]


class SolLiveLedgerError(RuntimeError):
    """A live ledger path, record, or existing history is invalid."""


@dataclass(frozen=True)
class SolLiveLedgerCursor:
    """Exact byte and sequence boundary for incremental ledger reads."""

    byte_offset: int
    next_sequence: int

    def __post_init__(self) -> None:
        if self.byte_offset < 0 or self.next_sequence <= 0:
            raise SolLiveLedgerError("live ledger cursor is invalid")


class SolLiveLedger:
    """Append durable, identity-stamped records without resetting history."""

    event_types = SOL_LIVE_EVENT_TYPES

    def __init__(
        self,
        *,
        path: Path | str,
        profile_id: str,
        profile_fingerprint: str,
        run_fingerprint: str,
        run_id: str,
        execution_mode: LedgerExecutionMode = "live",
    ) -> None:
        self.path = Path(path)
        if execution_mode not in {"live", "observe"}:
            raise SolLiveLedgerError("ledger execution_mode must be live or observe")
        self._execution_mode = execution_mode
        self._validate_path(self.path)
        self._profile_id = _required_text(profile_id, "profile_id")
        self._profile_fingerprint = _required_text(
            profile_fingerprint,
            "profile_fingerprint",
        )
        self._run_fingerprint = _required_text(run_fingerprint, "run_fingerprint")
        self._run_id = _required_text(run_id, "run_id")
        # One code per row this instance has validated or written, naming the
        # decoded (event_type, profile_fingerprint) pair, so a later selective
        # read can pass over rows it cannot select without decoding them again.
        self._envelope_codes = array("I")
        self._envelope_code_by_key: dict[object, int] = {}
        self._envelope_keys: list[tuple[object, object] | None] = [None]
        self._next_sequence = self._validated_record_count() + 1
        # Codes name line numbers only while every append starts a new line. An
        # unterminated last row would absorb the next append, so this instance
        # then decodes every row, exactly as a read without a declaration does.
        self._envelopes_aligned = _ends_with_newline(self.path)

    def append(
        self,
        *,
        event_type: str,
        observed_at_utc: str,
        live_armed: bool,
        execution_authority: str,
        payload: Mapping[str, object],
    ) -> Path:
        """Durably append one validated JSON record and return the ledger path."""
        if event_type not in self.event_types:
            raise SolLiveLedgerError(f"unknown live event_type: {event_type!r}")
        observed = _utc_timestamp(observed_at_utc)
        if not isinstance(live_armed, bool):
            raise SolLiveLedgerError("live_armed must be boolean")
        authority = _required_text(execution_authority, "execution_authority")
        if self._execution_mode == "observe" and (live_armed or authority != "none"):
            raise SolLiveLedgerError("observer ledger cannot be armed")
        if self._execution_mode == "live" and live_armed and authority == "none":
            raise SolLiveLedgerError("armed live record requires execution authority")
        clean_payload = _validated_payload(payload)
        record: dict[str, object] = {
            "schema_version": 1,
            "sequence": self._next_sequence,
            "event_type": event_type,
            "observed_at_utc": observed,
            "execution_mode": self._execution_mode,
            "effective_mode": (
                "OBSERVE ONLY"
                if self._execution_mode == "observe"
                else "LIVE ARMED"
                if live_armed
                else "DISARMED"
            ),
            "live_armed": live_armed,
            "execution_authority": authority,
            "profile_id": self._profile_id,
            "profile_fingerprint": self._profile_fingerprint,
            "run_fingerprint": self._run_fingerprint,
            "run_id": self._run_id,
            "payload": clean_payload,
        }
        self._append_record(record)
        self._remember_envelope(record)
        self._next_sequence += 1
        return self.path

    @property
    def run_id(self) -> str:
        """Return the immutable run identity stamped on new rows."""
        return self._run_id

    @property
    def profile_id(self) -> str:
        """Return the immutable execution-profile identity."""
        return self._profile_id

    @property
    def profile_fingerprint(self) -> str:
        """Return the immutable execution-profile fingerprint."""
        return self._profile_fingerprint

    @property
    def run_fingerprint(self) -> str:
        """Return the authority-sensitive run-contract fingerprint."""
        return self._run_fingerprint

    def _validate_path(self, path: Path) -> None:
        if self._execution_mode == "observe":
            _validate_observer_path(path)
        else:
            _validate_live_path(path)

    def read_all(self) -> list[dict[str, object]]:
        """Read and validate the complete existing ledger in sequence order."""
        return list(self._iter_records())

    def read_matching(
        self,
        predicate: Callable[[Mapping[str, object]], bool],
        *,
        event_types: Collection[object] | None = None,
        profile_fingerprint: str | None = None,
    ) -> list[dict[str, object]]:
        """Validate all rows while retaining only rows selected by ``predicate``.

        ``event_types`` and ``profile_fingerprint`` declare a necessary condition
        of ``predicate``: it must reject every row, other than the first, whose
        decoded event type is outside ``event_types`` or whose decoded profile
        fingerprint differs. A row this instance already validated (when it was
        constructed, or when it wrote the row) that fails the declaration is
        passed over without being decoded again; the first row and every other
        row are decoded, checked and offered to ``predicate`` exactly as without
        the declaration.
        """
        excluded = self._excluded_envelope_codes(event_types, profile_fingerprint)
        return [record for record in self._iter_records(excluded) if predicate(record)]

    def _validated_record_count(self) -> int:
        count = 0
        for record in self._iter_records():
            self._remember_envelope(record)
            count += 1
        return count

    def _remember_envelope(self, record: Mapping[str, object]) -> None:
        key = (record.get("event_type"), record.get("profile_fingerprint"))
        try:
            code = self._envelope_code_by_key.get(key)
        except TypeError:
            self._envelope_codes.append(_UNKNOWN_ENVELOPE)
            return
        if code is None:
            code = len(self._envelope_keys)
            self._envelope_code_by_key[key] = code
            self._envelope_keys.append(key)
        self._envelope_codes.append(code)

    def _excluded_envelope_codes(
        self,
        event_types: Collection[object] | None,
        profile_fingerprint: str | None,
    ) -> frozenset[int]:
        if not self._envelopes_aligned or (
            event_types is None and profile_fingerprint is None
        ):
            return frozenset()
        return frozenset(
            code
            for code, key in enumerate(self._envelope_keys)
            if key is not None
            and (
                (event_types is not None and key[0] not in event_types)
                or (profile_fingerprint is not None and key[1] != profile_fingerprint)
            )
        )

    def _iter_records(
        self, excluded: frozenset[int] = frozenset()
    ) -> Iterator[dict[str, object]]:
        if not self.path.exists():
            return
        codes = self._envelope_codes
        known = len(codes) if excluded else 0
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if 1 < line_number <= known and codes[line_number - 1] in excluded:
                    continue
                if not line.strip():
                    raise SolLiveLedgerError(f"live ledger line {line_number} is empty")
                record = _decode_record(line, line_number)
                if record.get("sequence") != line_number:
                    raise SolLiveLedgerError(
                        f"live ledger line {line_number} sequence must equal {line_number}"
                    )
                yield record

    def end_cursor(self) -> SolLiveLedgerCursor:
        """Return the current complete append boundary for this writer."""
        size = self.path.stat().st_size if self.path.exists() else 0
        return SolLiveLedgerCursor(size, self._next_sequence)

    def read_from_cursor(
        self,
        cursor: SolLiveLedgerCursor,
    ) -> tuple[list[dict[str, object]], SolLiveLedgerCursor]:
        """Read and validate only complete rows appended after ``cursor``."""
        size = self.path.stat().st_size if self.path.exists() else 0
        if size < cursor.byte_offset:
            raise SolLiveLedgerError("live ledger was truncated after cursor creation")
        if size == cursor.byte_offset:
            if cursor.next_sequence != self._next_sequence:
                raise SolLiveLedgerError("live ledger cursor sequence is stale")
            return [], cursor
        encoded = _read_suffix(self.path, cursor.byte_offset)
        rows = _decode_suffix(encoded, cursor.next_sequence)
        next_sequence = cursor.next_sequence + len(rows)
        if next_sequence != self._next_sequence:
            raise SolLiveLedgerError("live ledger changed outside its active writer")
        return rows, SolLiveLedgerCursor(
            cursor.byte_offset + len(encoded), next_sequence
        )

    def _append_record(self, record: Mapping[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            encoded = (
                json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise SolLiveLedgerError(f"live record is not JSON-safe: {exc}") from exc
        descriptor = os.open(
            self.path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            written = os.write(descriptor, encoded)
            if written != len(encoded):
                raise SolLiveLedgerError(
                    f"short live-ledger write: {written}/{len(encoded)} bytes"
                )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _validate_live_path(path: Path) -> None:
    parts = path.parts
    sol_domain = any(
        parts[index : index + 2] == ("live", "sol_range_onset_canary")
        for index in range(max(0, len(parts) - 1))
    )
    cohort_domain = any(
        parts[index : index + 2] == ("live", "bidirectional_cohort")
        for index in range(max(0, len(parts) - 1))
    )
    valid_name = path.name == "decisions.jsonl" or (
        cohort_domain and path.suffix == ".jsonl"
    )
    if not (sol_domain or cohort_domain) or not valid_name:
        raise SolLiveLedgerError(
            "live ledger path must use live/sol_range_onset_canary/decisions.jsonl "
            "or live/bidirectional_cohort/*.jsonl"
        )


def _validate_observer_path(path: Path) -> None:
    parts = path.parts
    observer_domain = any(
        parts[index] == "observe" for index in range(max(0, len(parts) - 1))
    )
    legacy_cohort_domain = any(
        parts[index : index + 2] == ("live", "bidirectional_cohort")
        for index in range(max(0, len(parts) - 1))
    )
    if path.name != "decisions.jsonl" or not (observer_domain or legacy_cohort_domain):
        raise SolLiveLedgerError(
            "observer ledger path must use observe/*/decisions.jsonl or the "
            "legacy live/bidirectional_cohort/decisions.jsonl"
        )


def _decode_record(line: str, line_number: int) -> dict[str, object]:
    try:
        value: object = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SolLiveLedgerError(
            f"live ledger line {line_number} is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SolLiveLedgerError(f"live ledger line {line_number} must be an object")
    _validate_json_value(value, path=f"line {line_number}")
    return value


def _ends_with_newline(path: Path) -> bool:
    """Report whether an append to ``path`` would start a new line."""
    try:
        with path.open("rb") as handle:
            if handle.seek(0, os.SEEK_END) == 0:
                return True
            handle.seek(-1, os.SEEK_END)
            return handle.read(1) == b"\n"
    except FileNotFoundError:
        return True


def _read_suffix(path: Path, offset: int) -> bytes:
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            encoded = handle.read()
    except OSError as exc:
        raise SolLiveLedgerError(f"unable to read live ledger suffix: {exc}") from exc
    if not encoded.endswith(b"\n"):
        raise SolLiveLedgerError("live ledger suffix ends with an incomplete row")
    return encoded


def _decode_suffix(encoded: bytes, first_sequence: int) -> list[dict[str, object]]:
    try:
        lines = encoded.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise SolLiveLedgerError("live ledger suffix is not valid UTF-8") from exc
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=first_sequence):
        if not line:
            raise SolLiveLedgerError(f"live ledger line {line_number} is empty")
        record = _decode_record(line, line_number)
        expected = first_sequence + len(records)
        if record.get("sequence") != expected:
            raise SolLiveLedgerError(
                f"live ledger line {line_number} sequence must equal {expected}"
            )
        records.append(record)
    return records


def _validated_payload(payload: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise SolLiveLedgerError("payload must be an object")
    result = dict(payload)
    _validate_json_value(result, path="payload")
    _reject_secret_keys(result, path="payload")
    return result


def _validate_json_value(value: object, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise SolLiveLedgerError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key, item in value.items():
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise SolLiveLedgerError(f"{path} contains a non-JSON value")


def _reject_secret_keys(value: Mapping[str, object], *, path: str) -> None:
    for key, item in value.items():
        normalized = key.lower().replace("-", "_")
        if any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS):
            raise SolLiveLedgerError(f"{path}.{key} is a secret-shaped field")
        if isinstance(item, dict):
            _reject_secret_keys(item, path=f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                if isinstance(child, dict):
                    _reject_secret_keys(child, path=f"{path}.{key}[{index}]")


def _utc_timestamp(value: str) -> str:
    text = _required_text(value, "observed_at_utc")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SolLiveLedgerError(
            "observed_at_utc must be an ISO-8601 UTC time"
        ) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise SolLiveLedgerError("observed_at_utc must use UTC, not a local offset")
    return parsed.isoformat()


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SolLiveLedgerError(f"{label} must be non-empty text")
    return value.strip()
