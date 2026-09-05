"""Report-only pre-close depth-ten pressure evidence for exact ``xyz:MU``."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Protocol

MU_PRESSURE_SOURCE = "hyperliquid_mainnet_l2_rest"
MU_SYMBOL = "xyz:MU"
SKHX_SYMBOL = "xyz:SKHX"
CL_SYMBOL = "xyz:CL"
SILVER_SYMBOL = "xyz:SILVER"
SP500_SYMBOL = "xyz:SP500"
SPCX_SYMBOL = "xyz:SPCX"
SNDK_SYMBOL = "xyz:SNDK"
_SUPPORTED_SYMBOLS = frozenset(
    (
        MU_SYMBOL,
        SKHX_SYMBOL,
        CL_SYMBOL,
        SILVER_SYMBOL,
        SP500_SYMBOL,
        SPCX_SYMBOL,
        SNDK_SYMBOL,
    )
)
_MAXIMUM_END_AGE_MS = 15_000
_DEFAULT_TAIL_BYTES = 512 * 1_024


@dataclass(frozen=True)
class MuPreclosePressureEvidence:
    """One completed-bar pressure fact with explicit causal provenance."""

    symbol: str
    bar_open_ms: int
    bar_close_ms: int
    observed_at_ms: int
    source: str
    last_exchange_ts_ms: int | None
    last_recv_ts_ms: int | None
    snapshot_count: int
    end_boundary_age_ms: int | None
    imbalance_10: float | None
    fresh: bool
    scan_complete: bool
    status: str
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject success-shaped or temporally inconsistent evidence."""
        if self.symbol not in _SUPPORTED_SYMBOLS or self.source != MU_PRESSURE_SOURCE:
            raise ValueError("HIP-3 pressure evidence identity is invalid")
        _ordered_times(self.bar_open_ms, self.bar_close_ms, self.observed_at_ms)
        _nonnegative_integer(self.snapshot_count, "snapshot_count")
        if not self.status.strip() or self.execution_authority != "none":
            raise ValueError("MU pressure evidence must remain report-only")
        if self.snapshot_count == 0:
            if any(
                value is not None
                for value in (
                    self.last_exchange_ts_ms,
                    self.last_recv_ts_ms,
                    self.end_boundary_age_ms,
                    self.imbalance_10,
                )
            ):
                raise ValueError("empty MU pressure evidence cannot publish a snapshot")
        else:
            self._validate_observation()
        if self.fresh and (
            not self.scan_complete
            or self.snapshot_count < 2
            or self.end_boundary_age_ms is None
            or self.end_boundary_age_ms > _MAXIMUM_END_AGE_MS
        ):
            raise ValueError("fresh MU pressure evidence violates its causal gate")

    def _validate_observation(self) -> None:
        """Validate the selected exchange and receipt timestamps."""
        exchange = _integer(self.last_exchange_ts_ms, "last_exchange_ts_ms")
        received = _integer(self.last_recv_ts_ms, "last_recv_ts_ms")
        age = _integer(self.end_boundary_age_ms, "end_boundary_age_ms")
        if not self.bar_open_ms <= exchange < self.bar_close_ms:
            raise ValueError("MU pressure exchange timestamp is outside the bar")
        if received > self.observed_at_ms:
            raise ValueError("MU pressure receipt timestamp exceeds observed time")
        if age != self.bar_close_ms - exchange:
            raise ValueError("MU pressure boundary age is inconsistent")
        imbalance = self.imbalance_10
        if imbalance is None or not math.isfinite(imbalance) or abs(imbalance) > 1.0:
            raise ValueError("MU depth-ten imbalance must be finite in [-1, 1]")


class MuPreclosePressureSourceProtocol(Protocol):
    """Return one causal pressure fact for an exact completed MU bar."""

    def completed_bar(
        self,
        symbol: str,
        *,
        bar_open_ms: int,
        bar_close_ms: int,
        observed_at_ms: int,
    ) -> MuPreclosePressureEvidence:
        """Return pre-close pressure without network calls or execution authority."""
        ...


@dataclass(frozen=True)
class MuAssetLedgerBinding:
    """Exact MU identity carried outside symbol-free asset payloads."""

    symbol: str
    path: Path
    profile_id: str

    def __post_init__(self) -> None:
        """Reject paths or profiles that could alias another HIP-3 asset."""
        if self.symbol not in _SUPPORTED_SYMBOLS:
            raise ValueError("HIP-3 asset ledger binding has unsupported symbol")
        token = self.symbol.lower()
        if token not in self.profile_id.lower():
            raise ValueError("HIP-3 asset ledger profile must identify its symbol")
        if token not in self.path.name.lower():
            raise ValueError("HIP-3 asset ledger path must identify its symbol")


@dataclass(frozen=True)
class _Book:
    exchange_ts_ms: int
    recv_ts_ms: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]

    @property
    def market_identity(self) -> tuple[object, ...]:
        return (self.exchange_ts_ms, self.bids, self.asks)

    @property
    def imbalance_10(self) -> float:
        bid = sum(level[1] for level in self.bids)
        ask = sum(level[1] for level in self.asks)
        return (bid - ask) / (bid + ask)


@dataclass(frozen=True)
class _LedgerScan:
    books: tuple[_Book, ...]
    reached_bar_open: bool


class MuHip3LedgerPreclosePressureSource:
    """Read exact pre-close pressure from existing asset and cohort ledgers."""

    def __init__(
        self,
        *,
        asset_binding: MuAssetLedgerBinding,
        cohort_ledger: Path,
        tail_bytes: int = _DEFAULT_TAIL_BYTES,
    ) -> None:
        """Bind read-only ledgers and a bounded reverse-scan capacity."""
        if isinstance(tail_bytes, bool) or not isinstance(tail_bytes, int):
            raise ValueError("MU pressure tail_bytes must be a positive integer")
        if tail_bytes <= 0:
            raise ValueError("MU pressure tail_bytes must be a positive integer")
        self._asset_binding = asset_binding
        self._cohort_ledger = cohort_ledger
        self._tail_bytes = tail_bytes

    def completed_bar(
        self,
        symbol: str,
        *,
        bar_open_ms: int,
        bar_close_ms: int,
        observed_at_ms: int,
    ) -> MuPreclosePressureEvidence:
        """Return canonical last-pre-close pressure or an unresolved fact."""
        if symbol != self._asset_binding.symbol:
            raise ValueError(
                f"HIP-3 pre-close pressure requires exact {self._asset_binding.symbol}"
            )
        _ordered_times(bar_open_ms, bar_close_ms, observed_at_ms)
        scans = (
            self._scan(
                self._asset_binding.path,
                symbol,
                bar_open_ms,
                observed_at_ms,
                False,
            ),
            self._scan(self._cohort_ledger, symbol, bar_open_ms, observed_at_ms, True),
        )
        books = _canonical_books(
            book
            for scan in scans
            for book in scan.books
            if bar_open_ms <= book.exchange_ts_ms < bar_close_ms
        )
        scan_complete = all(scan.reached_bar_open for scan in scans)
        return _evidence(
            symbol,
            bar_open_ms,
            bar_close_ms,
            observed_at_ms,
            books,
            scan_complete,
        )

    def _scan(
        self,
        path: Path,
        symbol: str,
        bar_open_ms: int,
        observed_at_ms: int,
        cohort: bool,
    ) -> _LedgerScan:
        rows, _full_file = _reverse_rows(path, self._tail_bytes)
        books: list[_Book] = []
        reached = False
        newest_receipt: int | None = None
        chronology_valid = True
        relevant_seen = False
        for row in rows:
            payload = _book_payload(row, symbol, cohort)
            if payload is None:
                continue
            relevant_seen = True
            receipt = _integer(payload.get("recv_ts_ms"), "recv_ts_ms")
            if receipt > observed_at_ms:
                continue
            if not cohort and row.get("profile_id") != self._asset_binding.profile_id:
                raise ValueError("MU asset ledger profile identity is inconsistent")
            book = _book(payload, require_symbol=cohort, expected_symbol=symbol)
            if newest_receipt is not None and book.recv_ts_ms > newest_receipt:
                chronology_valid = False
            newest_receipt = book.recv_ts_ms
            if book.recv_ts_ms < bar_open_ms:
                reached = True
            books.append(book)
        if cohort and not relevant_seen:
            reached = True
        return _LedgerScan(tuple(books), reached and chronology_valid)


def _evidence(
    symbol: str,
    bar_open_ms: int,
    bar_close_ms: int,
    observed_at_ms: int,
    books: tuple[_Book, ...],
    scan_complete: bool,
) -> MuPreclosePressureEvidence:
    last = max(books, key=lambda value: value.exchange_ts_ms, default=None)
    count = len(books)
    age = None if last is None else bar_close_ms - last.exchange_ts_ms
    fresh = bool(scan_complete and count >= 2 and age is not None and age <= 15_000)
    status = _status(scan_complete, count, age)
    return MuPreclosePressureEvidence(
        symbol,
        bar_open_ms,
        bar_close_ms,
        observed_at_ms,
        MU_PRESSURE_SOURCE,
        None if last is None else last.exchange_ts_ms,
        None if last is None else last.recv_ts_ms,
        count,
        age,
        None if last is None else last.imbalance_10,
        fresh,
        scan_complete,
        status,
    )


def _status(complete: bool, count: int, age: int | None) -> str:
    if not complete:
        return "truncated_ledger_tail"
    if count == 0:
        return "no_snapshots"
    if count < 2:
        return "insufficient_snapshots"
    if age is None or age > _MAXIMUM_END_AGE_MS:
        return "stale"
    return "fresh"


def _canonical_books(values: object) -> tuple[_Book, ...]:
    canonical: dict[int, _Book] = {}
    for book in values:
        if not isinstance(book, _Book):
            raise TypeError("MU canonical pressure values must be books")
        existing = canonical.get(book.exchange_ts_ms)
        if existing is not None and existing.market_identity != book.market_identity:
            raise ValueError("MU pressure has a conflicting exchange timestamp")
        if existing is None or book.recv_ts_ms < existing.recv_ts_ms:
            canonical[book.exchange_ts_ms] = book
    return tuple(canonical[key] for key in sorted(canonical))


def _book_payload(
    row: dict[str, object], symbol: str, cohort: bool
) -> dict[str, object] | None:
    expected = "market_books" if cohort else "book_observation"
    if row.get("event_type") != expected:
        return None
    payload = _mapping(row.get("payload"), "MU ledger payload")
    if cohort:
        books = _mapping(payload.get("books"), "MU cohort books")
        raw = books.get(symbol)
        return None if raw is None else _mapping(raw, "MU cohort book")
    return payload


def _book(
    payload: dict[str, object],
    *,
    require_symbol: bool,
    expected_symbol: str,
) -> _Book:
    if payload.get("source") != MU_PRESSURE_SOURCE:
        raise ValueError("MU pressure source must be Hyperliquid mainnet L2")
    symbol = payload.get("symbol")
    if (require_symbol and symbol != expected_symbol) or symbol not in {
        None,
        expected_symbol,
    }:
        raise ValueError(
            f"HIP-3 pressure book must have exact {expected_symbol} identity"
        )
    exchange_ts_ms = _integer(payload.get("exchange_ts_ms"), "exchange_ts_ms")
    recv_ts_ms = _integer(payload.get("recv_ts_ms"), "recv_ts_ms")
    if recv_ts_ms < exchange_ts_ms:
        raise ValueError("MU pressure receipt timestamp precedes exchange timestamp")
    book = _Book(
        exchange_ts_ms,
        recv_ts_ms,
        _levels(payload.get("bids"), "bids"),
        _levels(payload.get("asks"), "asks"),
    )
    _validate_book_shape(book)
    return book


def _validate_book_shape(book: _Book) -> None:
    bid_prices = tuple(level[0] for level in book.bids)
    ask_prices = tuple(level[0] for level in book.asks)
    bids_ordered = all(left > right for left, right in zip(bid_prices, bid_prices[1:]))
    asks_ordered = all(left < right for left, right in zip(ask_prices, ask_prices[1:]))
    if not bids_ordered or not asks_ordered or bid_prices[0] >= ask_prices[0]:
        raise ValueError("MU pressure levels must be ordered and non-crossed")


def _levels(value: object, side: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) < 10:
        raise ValueError(f"MU pressure {side} require at least ten levels")
    output: list[tuple[float, float]] = []
    for raw in value[:10]:
        level = _mapping(raw, f"MU pressure {side} level")
        price = _positive_number(level.get("price"), f"{side} price")
        size = _positive_number(level.get("size"), f"{side} size")
        output.append((price, size))
    return tuple(output)


def _reverse_rows(
    path: Path, tail_bytes: int
) -> tuple[tuple[dict[str, object], ...], bool]:
    if not path.is_file():
        return (), True
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        start = max(0, size - tail_bytes)
        handle.seek(start)
        data = handle.read()
    if start and b"\n" in data:
        data = data.split(b"\n", 1)[1]
    elif start:
        return (), False
    lines = tuple(line for line in data.splitlines() if line.strip())
    return tuple(_json_object(line) for line in reversed(lines)), start == 0


def _json_object(line: bytes) -> dict[str, object]:
    try:
        value = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("MU pressure ledger contains malformed JSONL") from exc
    if not isinstance(value, dict):
        raise ValueError("MU pressure ledger row must be an object")
    return value


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"MU pressure {label} must be a nonnegative integer")
    return value


def _nonnegative_integer(value: object, label: str) -> None:
    _integer(value, label)


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"MU pressure {label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"MU pressure {label} must be finite and positive")
    return numeric


def _ordered_times(open_ms: int, close_ms: int, observed_ms: int) -> None:
    for value, label in (
        (open_ms, "bar_open_ms"),
        (close_ms, "bar_close_ms"),
        (observed_ms, "observed_at_ms"),
    ):
        _nonnegative_integer(value, label)
    if not open_ms < close_ms <= observed_ms:
        raise ValueError("MU pressure times must satisfy open < close <= observed")
