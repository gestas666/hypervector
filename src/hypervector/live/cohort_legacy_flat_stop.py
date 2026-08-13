"""Fail-closed flat-boundary detection for one legacy cohort transition."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time


class LegacyFlatStopError(RuntimeError):
    """The legacy cohort cannot prove a safe, exact-run stop boundary."""


class LegacyFlatBoundaryPending(LegacyFlatStopError):
    """The exact cohort remains healthy but is not flat and order-free yet."""


@dataclass(frozen=True)
class LegacyFlatStopEvidence:
    """Exact venue-backed cohort identity observed flat and order-free."""

    run_id: str
    profile_fingerprint: str
    observed_at_utc: str
    symbols: tuple[str, ...]
    source_sequence: int


def evaluate_legacy_flat_snapshot(
    record: Mapping[str, object],
    *,
    expected_profile_fingerprint: str,
    expected_run_id: str,
    expected_symbols: tuple[str, ...],
) -> LegacyFlatStopEvidence | None:
    """Return exact flat evidence or reject an unsafe cohort snapshot."""
    if record.get("event_type") != "cohort_snapshot":
        return None
    _validate_expected_identity(
        expected_profile_fingerprint,
        expected_run_id,
        expected_symbols,
    )
    _require_equal(
        record.get("profile_fingerprint"),
        expected_profile_fingerprint,
        "profile fingerprint",
    )
    _require_equal(record.get("run_id"), expected_run_id, "run id")
    _require_equal(record.get("execution_mode"), "live", "execution mode")
    if record.get("live_armed") is not True:
        raise LegacyFlatStopError("cohort snapshot is not explicitly live armed")
    payload = _mapping(record.get("payload"), "cohort snapshot payload")
    _require_zero_open_count(payload.get("open_position_count"))
    symbols = _validate_assets(payload.get("assets"), expected_symbols)
    sequence = _positive_integer(record.get("sequence"), "source sequence")
    observed = _required_text(record.get("observed_at_utc"), "observation time")
    return LegacyFlatStopEvidence(
        run_id=expected_run_id,
        profile_fingerprint=expected_profile_fingerprint,
        observed_at_utc=observed,
        symbols=symbols,
        source_sequence=sequence,
    )


def watch_legacy_flat_boundary(
    ledger: Path,
    *,
    expected_profile_fingerprint: str,
    expected_run_id: str,
    expected_symbols: tuple[str, ...],
    poll_seconds: float = 0.1,
    timeout_seconds: float | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> LegacyFlatStopEvidence:
    """Wait from the current EOF for the next exact flat cohort snapshot."""
    _validate_watch_timing(poll_seconds, timeout_seconds)
    if not ledger.is_file():
        raise LegacyFlatStopError(f"cohort ledger not found: {ledger}")
    deadline = None if timeout_seconds is None else monotonic_fn() + timeout_seconds
    with ledger.open("rb") as stream:
        stream.seek(0, 2)
        buffered = b""
        while True:
            _reject_truncation(ledger, stream.tell())
            buffered, evidence = _consume_append(
                stream.read(),
                buffered,
                expected_profile_fingerprint,
                expected_run_id,
                expected_symbols,
            )
            if evidence is not None:
                return evidence
            if deadline is not None and monotonic_fn() >= deadline:
                raise LegacyFlatStopError("timed out awaiting an exact flat snapshot")
            sleep_fn(poll_seconds)


def write_legacy_stop_request(
    stop_path: Path,
    evidence: LegacyFlatStopEvidence,
) -> None:
    """Create one exclusive STOP request without overwriting operator state."""
    if not stop_path.parent.is_dir():
        raise LegacyFlatStopError(
            f"operator stop directory not found: {stop_path.parent}"
        )
    payload = {
        "schema_version": 1,
        "reason": "legacy_flat_transition",
        **asdict(evidence),
    }
    try:
        with stop_path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
    except FileExistsError as exc:
        raise LegacyFlatStopError(
            f"operator stop request already exists: {stop_path}"
        ) from exc
    except PermissionError as exc:
        raise LegacyFlatStopError(
            f"operator stop request is not writable: {stop_path}"
        ) from exc


def _consume_append(
    chunk: bytes,
    buffered: bytes,
    profile: str,
    run_id: str,
    symbols: tuple[str, ...],
) -> tuple[bytes, LegacyFlatStopEvidence | None]:
    combined = buffered + chunk
    lines = combined.split(b"\n")
    tail = lines.pop()
    for line in lines:
        if not line:
            continue
        record = _decode_record(line)
        try:
            evidence = evaluate_legacy_flat_snapshot(
                record,
                expected_profile_fingerprint=profile,
                expected_run_id=run_id,
                expected_symbols=symbols,
            )
        except LegacyFlatBoundaryPending:
            continue
        if evidence is not None:
            return tail, evidence
    return tail, None


def _decode_record(line: bytes) -> Mapping[str, object]:
    try:
        decoded = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyFlatStopError("new cohort ledger row is malformed") from exc
    return _mapping(decoded, "cohort ledger row")


def _validate_assets(
    raw: object,
    expected_symbols: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise LegacyFlatStopError("cohort snapshot assets must be a list")
    observed: list[str] = []
    for item in raw:
        asset = _mapping(item, "cohort snapshot asset")
        symbol = _required_text(asset.get("symbol"), "asset symbol")
        _validate_flat_asset(symbol, asset)
        observed.append(symbol)
    if len(set(observed)) != len(observed):
        raise LegacyFlatStopError("cohort snapshot assets contain duplicates")
    if set(observed) != set(expected_symbols):
        raise LegacyFlatStopError("cohort snapshot asset coverage differs")
    return expected_symbols


def _validate_flat_asset(symbol: str, asset: Mapping[str, object]) -> None:
    if asset.get("last_fault") is not None:
        raise LegacyFlatStopError(f"{symbol} retains a fault")
    if asset.get("state") != "FLAT":
        raise LegacyFlatBoundaryPending(f"{symbol} is not flat")
    size = _finite_number(asset.get("position_size_signed"), f"{symbol} position")
    if size != 0.0:
        raise LegacyFlatBoundaryPending(f"{symbol} has a nonzero position")
    owned = tuple(asset.get(key) for key in _owned_order_keys())
    if any(value is not None for value in owned):
        raise LegacyFlatBoundaryPending(f"{symbol} retains an owned order")


def _owned_order_keys() -> tuple[str, ...]:
    return "entry_oid", "stop_oid", "target_oid", "close_oid"


def _validate_expected_identity(
    profile: str,
    run_id: str,
    symbols: tuple[str, ...],
) -> None:
    if len(profile) != 64 or any(
        character not in "0123456789abcdef" for character in profile
    ):
        raise LegacyFlatStopError("expected profile fingerprint is invalid")
    _required_text(run_id, "expected run id")
    if not symbols or len(set(symbols)) != len(symbols):
        raise LegacyFlatStopError("expected symbols must be unique and non-empty")


def _validate_watch_timing(poll_seconds: float, timeout_seconds: float | None) -> None:
    if not math.isfinite(poll_seconds) or poll_seconds <= 0.0:
        raise LegacyFlatStopError("poll seconds must be positive and finite")
    if timeout_seconds is not None and (
        not math.isfinite(timeout_seconds) or timeout_seconds <= 0.0
    ):
        raise LegacyFlatStopError("timeout seconds must be positive and finite")


def _reject_truncation(path: Path, offset: int) -> None:
    try:
        size = path.stat().st_size
    except FileNotFoundError as exc:
        raise LegacyFlatStopError("cohort ledger disappeared while watching") from exc
    if size < offset:
        raise LegacyFlatStopError("cohort ledger truncated while watching")


def _require_zero_open_count(value: object) -> None:
    count = _positive_or_zero_integer(value, "open position count")
    if count != 0:
        raise LegacyFlatBoundaryPending("cohort snapshot reports an open position")


def _positive_integer(value: object, label: str) -> int:
    number = _positive_or_zero_integer(value, label)
    if number < 1:
        raise LegacyFlatStopError(f"{label} must be positive")
    return number


def _positive_or_zero_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LegacyFlatStopError(f"{label} must be a nonnegative integer")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LegacyFlatStopError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise LegacyFlatStopError(f"{label} must be finite")
    return number


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LegacyFlatStopError(f"{label} must be an object")
    return value


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LegacyFlatStopError(f"{label} must be non-empty text")
    return value.strip()


def _require_equal(value: object, expected: str, label: str) -> None:
    if value != expected:
        raise LegacyFlatStopError(f"cohort snapshot {label} differs")
