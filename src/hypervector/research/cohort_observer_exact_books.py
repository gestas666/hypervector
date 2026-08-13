"""Fail-closed exact-book adapter for report-only cohort observer ledgers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from hypervector.research.cohort_live_audit_values import event_rows, payload, text

Record = Mapping[str, object]
_STRATEGY_NAME = "multi_asset_bidirectional_cohort"
_BOOK_SOURCE = "hyperliquid_mainnet_l2_rest"


def select_report_only_observer_run(
    records: Sequence[Record], requested: str | None = None
) -> tuple[tuple[Record, ...], Record]:
    """Return one exact report-only observe run and its configuration identity."""
    identities = [
        row
        for row in event_rows(records, "configuration_identity")
        if _is_report_only_observe(row)
    ]
    chosen = requested or (_run_id(identities[-1]) if identities else None)
    if chosen is None:
        raise ValueError("cohort research found no report-only observe run")
    selected = tuple(row for row in records if row.get("run_id") == chosen)
    if not selected or not all(_is_report_only_observe(row) for row in selected):
        raise ValueError(f"run {chosen} is not a report-only observe run")
    run_identities = event_rows(selected, "configuration_identity")
    if len(run_identities) != 1:
        raise ValueError(f"run {chosen} requires exactly one configuration identity")
    identity = run_identities[0]
    _validate_identity(identity, chosen)
    _validate_run_envelope(selected, identity)
    return selected, identity


def select_compatible_report_only_observer_runs(
    records: Sequence[Record], requested: str
) -> tuple[tuple[Record, ...], tuple[Record, ...]]:
    """Extend one observer run through later exact-contract restarts."""
    _, origin = select_report_only_observer_run(records, requested)
    identities = list(event_rows(records, "configuration_identity"))
    origin_index = next(
        index for index, row in enumerate(identities) if _run_id(row) == requested
    )
    compatible: list[Record] = []
    allowed: set[str] = set()
    contract = _continuation_contract(origin)
    for candidate in identities[origin_index:]:
        run = _run_id(candidate)
        _, validated = select_report_only_observer_run(records, run)
        if _continuation_contract(validated) != contract:
            raise ValueError(f"observer run {run} continuation identity differs")
        compatible.append(validated)
        allowed.add(run)
    selected = tuple(row for row in records if row.get("run_id") in allowed)
    return selected, tuple(compatible)


def extract_observer_asset_books(
    records: Sequence[Record], symbols: Sequence[str]
) -> dict[str, tuple[dict[str, object], ...]]:
    """Expand embedded observer market books into exact asset book observations."""
    required = _required_symbols(symbols)
    output: dict[str, list[dict[str, object]]] = {symbol: [] for symbol in required}
    seen: dict[str, set[int]] = {symbol: set() for symbol in required}
    for row in event_rows(records, "market_books"):
        _append_market_books(row, output, seen)
    missing = sorted(symbol for symbol, rows in output.items() if not rows)
    if missing:
        raise ValueError(f"observer market books missing required symbols: {missing}")
    return {symbol: tuple(rows) for symbol, rows in output.items()}


def _append_market_books(
    row: Record,
    output: dict[str, list[dict[str, object]]],
    seen: dict[str, set[int]],
) -> None:
    if not _is_report_only_observe(row):
        raise ValueError("market book row is not report-only observe evidence")
    books = _mapping(payload(row).get("books"), "observer books")
    observed_at_ms = _observed_at_ms(row)
    for symbol in output:
        raw = books.get(symbol)
        if raw is None:
            continue
        book = dict(_mapping(raw, f"observer {symbol} book"))
        recv_ms = _validate_book(book, symbol, observed_at_ms)
        if recv_ms in seen[symbol]:
            raise ValueError(f"duplicate {symbol} book receive timestamp: {recv_ms}")
        seen[symbol].add(recv_ms)
        output[symbol].append(_asset_row(row, book))


def _validate_book(book: Record, symbol: str, observed_at_ms: int) -> int:
    if book.get("symbol") != symbol:
        raise ValueError(f"observer {symbol} book symbol identity is invalid")
    if book.get("source") != _BOOK_SOURCE:
        raise ValueError(f"observer {symbol} book source is invalid")
    recv_ms = _nonnegative_int(book.get("recv_ts_ms"), f"{symbol} receive time")
    exchange_ms = _nonnegative_int(
        book.get("exchange_ts_ms"), f"{symbol} exchange time"
    )
    if exchange_ms > recv_ms or recv_ms > observed_at_ms:
        raise ValueError(f"observer {symbol} book chronology is invalid")
    _sequence(book.get("bids"), f"{symbol} bids")
    _sequence(book.get("asks"), f"{symbol} asks")
    return recv_ms


def _asset_row(row: Record, book: dict[str, object]) -> dict[str, object]:
    return {
        **dict(row),
        "event_type": "book_observation",
        "payload": book,
    }


def _validate_identity(identity: Record, chosen: str) -> None:
    values = payload(identity)
    if values.get("strategy_name") != _STRATEGY_NAME:
        raise ValueError(f"run {chosen} has unexpected cohort strategy identity")
    fingerprint = text(identity.get("profile_fingerprint"), "profile fingerprint")
    if values.get("profile_fingerprint") != fingerprint:
        raise ValueError(f"run {chosen} profile fingerprint is inconsistent")


def _validate_run_envelope(records: Sequence[Record], identity: Record) -> None:
    expected = {
        field: text(identity.get(field), f"observer {field}")
        for field in ("profile_id", "profile_fingerprint", "run_fingerprint")
    }
    for row in records:
        for field, value in expected.items():
            if row.get(field) != value:
                label = field.replace("_", " ")
                raise ValueError(f"observer run {label} is inconsistent")


def _continuation_contract(identity: Record) -> tuple[object, ...]:
    return (
        identity.get("profile_id"),
        identity.get("profile_fingerprint"),
        identity.get("run_fingerprint"),
        identity.get("execution_mode"),
        identity.get("effective_mode"),
        identity.get("live_armed"),
        identity.get("execution_authority"),
        payload(identity),
    )


def _is_report_only_observe(row: Record) -> bool:
    return (
        row.get("execution_mode") == "observe"
        and row.get("effective_mode") == "OBSERVE ONLY"
        and row.get("live_armed") is False
        and row.get("execution_authority") == "none"
    )


def _run_id(row: Record) -> str:
    return text(row.get("run_id"), "observer run id")


def _required_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    required = tuple(text(symbol, "required symbol") for symbol in symbols)
    if not required or len(set(required)) != len(required):
        raise ValueError("required observer symbols must be unique and non-empty")
    return required


def _observed_at_ms(row: Record) -> int:
    raw = text(row.get("observed_at_utc"), "observer book observed time")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("observer book observed time must include a timezone")
    return int(value.astimezone(timezone.utc).timestamp() * 1_000)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError(f"{label} must be a non-empty sequence")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
