"""Bounded 0xArchive history acquisition for Hyperliquid core markets."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

import requests


API_ROOT = "https://api.0xarchive.io/v1/hyperliquid"
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{0,63}$")


class OxaHistoryError(RuntimeError):
    """An actionable 0xArchive transport or HTTP boundary failure."""


class _HttpResponse(Protocol):
    status_code: int

    def json(self) -> object: ...


class _HttpSession(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, int | str],
        timeout: float,
    ) -> _HttpResponse: ...


@dataclass(frozen=True)
class OxaBookRequest:
    """Explicit bounds for a native Hyperliquid L2 history request."""

    symbol: str
    start: datetime
    end: datetime
    depth: int = 20
    limit: int = 1000
    max_pages: int = 1
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not _SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("symbol must be an uppercase Hyperliquid asset identifier")
        if self.start.tzinfo is not UTC or self.end.tzinfo is not UTC:
            raise ValueError("start and end must use the UTC timezone")
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if not 1 <= self.depth <= 20:
            raise ValueError("depth must be between 1 and 20")
        if not 1 <= self.limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def params(self, cursor: str | None = None) -> dict[str, int | str]:
        """Build vendor query parameters without credential material."""
        values: dict[str, int | str] = {
            "start": int(self.start.timestamp() * 1000),
            "end": int(self.end.timestamp() * 1000),
            "depth": self.depth,
            "limit": self.limit,
        }
        if cursor is not None:
            values["cursor"] = cursor
        return values


@dataclass(frozen=True)
class OxaLevel:
    """One validated native Hyperliquid price level."""

    px: str
    sz: str
    n: int

    def as_dict(self) -> dict[str, object]:
        """Return the existing replay JSONL level structure."""
        return {"px": self.px, "sz": self.sz, "n": self.n}


@dataclass(frozen=True)
class OxaBookSnapshot:
    """Validated point-in-time native Hyperliquid L2 snapshot."""

    symbol: str
    timestamp: str
    ts_exchange_ms: int
    bids: tuple[OxaLevel, ...]
    asks: tuple[OxaLevel, ...]

    def to_replay_row(self, *, request_id: str) -> dict[str, object]:
        """Return replay-compatible JSON without a fabricated receive time."""
        return {
            "ts_exchange_ms": self.ts_exchange_ms,
            "symbol": self.symbol,
            "source": "0xarchive_hyperliquid_native_l2",
            "vendor_request_id": request_id,
            "best_bid": self.bids[0].px,
            "best_ask": self.asks[0].px,
            "n_bids": len(self.bids),
            "n_asks": len(self.asks),
            "bids": [level.as_dict() for level in self.bids],
            "asks": [level.as_dict() for level in self.asks],
        }


@dataclass(frozen=True)
class OxaBookPage:
    """One validated response envelope with its vendor provenance."""

    request_id: str
    next_cursor: str | None
    snapshots: tuple[OxaBookSnapshot, ...]
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class OxaBookFetch:
    """Bounded page set and its explicit continuation state."""

    pages: tuple[OxaBookPage, ...]
    snapshots: tuple[OxaBookSnapshot, ...]
    complete: bool
    continuation_cursor: str | None

    @property
    def request_ids(self) -> tuple[str, ...]:
        """Return vendor correlation identifiers in request order."""
        return tuple(page.request_id for page in self.pages)


@dataclass(frozen=True)
class OxaStoredHistory:
    """Published evidence and replay paths."""

    directory: Path
    books_path: Path
    manifest_path: Path


class OxaHistoryClient:
    """Authenticated REST boundary for historical 0xArchive requests."""

    def __init__(
        self,
        *,
        api_key: str,
        session: _HttpSession | None = None,
    ) -> None:
        key = api_key.strip()
        if not key:
            raise ValueError("OXA_API_KEY is required")
        self._api_key = key
        self._session = session or requests.Session()

    def fetch_page(
        self,
        request: OxaBookRequest,
        *,
        cursor: str | None = None,
    ) -> OxaBookPage:
        """Fetch one bounded page and retain its raw evidence envelope."""
        try:
            response = self._session.get(
                f"{API_ROOT}/orderbook/{request.symbol}/history",
                headers={"X-API-Key": self._api_key},
                params=request.params(cursor),
                timeout=request.timeout_seconds,
            )
        except requests.RequestException as exc:
            name = type(exc).__name__
            raise OxaHistoryError(
                f"0xArchive network request failed ({name})"
            ) from None
        if response.status_code != 200:
            raise OxaHistoryError(
                f"0xArchive request failed with HTTP {response.status_code}"
            )
        return _parse_page(response.json(), request)


def fetch_orderbook_history(
    client: OxaHistoryClient, request: OxaBookRequest
) -> OxaBookFetch:
    """Fetch and validate no more than the explicitly bounded page count."""
    pages: list[OxaBookPage] = []
    cursor: str | None = None
    for _ in range(request.max_pages):
        page = client.fetch_page(request, cursor=cursor)
        pages.append(page)
        cursor = page.next_cursor
        if cursor is None:
            break
    snapshots = _merge_page_snapshots(pages)
    return OxaBookFetch(
        pages=tuple(pages),
        snapshots=snapshots,
        complete=cursor is None,
        continuation_cursor=cursor,
    )


def output_directory(data_root: Path | str, request: OxaBookRequest) -> Path:
    """Return the deterministic immutable directory for one requested window."""
    start, end = map(_window_stamp, (request.start, request.end))
    window = f"{start}_{end}_d{request.depth}"
    return (
        Path(data_root)
        / "cache"
        / "vendor"
        / "0xarchive"
        / "hyperliquid"
        / request.symbol
        / window
    )


def store_orderbook_history(
    data_root: Path | str,
    request: OxaBookRequest,
    result: OxaBookFetch,
) -> OxaStoredHistory:
    """Atomically publish raw pages, checksums, manifest, and replay JSONL."""
    final = output_directory(data_root, request)
    if final.exists():
        raise FileExistsError(f"0xArchive output already exists: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=final.parent))
    published = False
    try:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        files = _write_raw_pages(raw_dir, result.pages)
        books_path = staging / "books.jsonl"
        _write_books(books_path, result)
        files["books.jsonl"] = _file_evidence(books_path)
        manifest_path = staging / "manifest.json"
        manifest = _manifest(request, result, files)
        _write_json(manifest_path, manifest)
        staging.rename(final)
        published = True
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)
    return OxaStoredHistory(
        directory=final,
        books_path=final / "books.jsonl",
        manifest_path=final / "manifest.json",
    )


def acquire_and_store_orderbooks(
    *,
    data_root: Path | str,
    api_key: str,
    request: OxaBookRequest,
) -> dict[str, object]:
    """Acquire a bounded native L2 window and return a secret-free report."""
    result = fetch_orderbook_history(OxaHistoryClient(api_key=api_key), request)
    stored = store_orderbook_history(data_root, request, result)
    observed_start = result.snapshots[0].timestamp if result.snapshots else None
    observed_end = result.snapshots[-1].timestamp if result.snapshots else None
    return {
        "ok": True,
        "source": "0xarchive_hyperliquid_native_l2",
        "venue": "hyperliquid",
        "symbol": request.symbol,
        "directory": str(stored.directory.resolve()),
        "books_path": str(stored.books_path.resolve()),
        "manifest_path": str(stored.manifest_path.resolve()),
        "request_ids": list(result.request_ids),
        "page_count": len(result.pages),
        "row_count": len(result.snapshots),
        "observed_start": observed_start,
        "observed_end": observed_end,
        "complete": result.complete,
        "continuation_cursor": result.continuation_cursor,
    }


def _merge_page_snapshots(
    pages: list[OxaBookPage],
) -> tuple[OxaBookSnapshot, ...]:
    observed: dict[int, OxaBookSnapshot] = {}
    for page in pages:
        for snapshot in page.snapshots:
            existing = observed.get(snapshot.ts_exchange_ms)
            if existing is not None and existing != snapshot:
                raise ValueError(
                    "conflicting duplicate exchange timestamp across pages"
                )
            observed[snapshot.ts_exchange_ms] = snapshot
    return tuple(observed[timestamp] for timestamp in sorted(observed))


def _window_stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S%fZ")


def _write_raw_pages(
    raw_dir: Path, pages: tuple[OxaBookPage, ...]
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    for index, page in enumerate(pages, start=1):
        path = raw_dir / f"page-{index:04d}.json"
        _write_json(path, page.raw_payload)
        evidence[f"raw/{path.name}"] = _file_evidence(path)
    return evidence


def _write_books(path: Path, result: OxaBookFetch) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for snapshot in result.snapshots:
            request_id = next(
                page.request_id for page in result.pages if snapshot in page.snapshots
            )
            row = snapshot.to_replay_row(request_id=request_id)
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def _manifest(
    request: OxaBookRequest,
    result: OxaBookFetch,
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    observed_start = result.snapshots[0].timestamp if result.snapshots else None
    observed_end = result.snapshots[-1].timestamp if result.snapshots else None
    return {
        "schema_version": 1,
        "source": "0xarchive_hyperliquid_native_l2",
        "source_api": f"{API_ROOT}/orderbook/{{symbol}}/history",
        "venue": "hyperliquid",
        "symbol": request.symbol,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "requested_depth": request.depth,
        "page_limit": request.limit,
        "max_pages": request.max_pages,
        "request_ids": list(result.request_ids),
        "page_count": len(result.pages),
        "row_count": len(result.snapshots),
        "observed_start": observed_start,
        "observed_end": observed_end,
        "complete": result.complete,
        "continuation_cursor": result.continuation_cursor,
        "files": files,
    }


def _write_json(path: Path, payload: object) -> None:
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")


def _file_evidence(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def _parse_page(payload: object, request: OxaBookRequest) -> OxaBookPage:
    if not isinstance(payload, dict):
        raise ValueError("0xArchive response must be a JSON object")
    data = payload.get("data")
    meta = payload.get("meta")
    if payload.get("success") is not True or not isinstance(data, list):
        raise ValueError("0xArchive response did not contain successful data")
    request_id = meta.get("request_id") if isinstance(meta, dict) else None
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("0xArchive response is missing meta.request_id")
    next_cursor = meta.get("next_cursor")
    if next_cursor is not None and not isinstance(next_cursor, str):
        raise ValueError("0xArchive meta.next_cursor must be a string or null")
    snapshots = _parse_snapshots(data, request)
    return OxaBookPage(
        request_id=request_id,
        next_cursor=next_cursor,
        snapshots=snapshots,
        raw_payload=payload,
    )


def _parse_snapshots(
    records: list[object], request: OxaBookRequest
) -> tuple[OxaBookSnapshot, ...]:
    by_timestamp: dict[int, OxaBookSnapshot] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("0xArchive data must contain JSON objects")
        snapshot = _parse_snapshot(record, request)
        existing = by_timestamp.get(snapshot.ts_exchange_ms)
        if existing is not None and existing != snapshot:
            raise ValueError("conflicting duplicate exchange timestamp")
        by_timestamp[snapshot.ts_exchange_ms] = snapshot
    return tuple(by_timestamp[timestamp] for timestamp in sorted(by_timestamp))


def _parse_snapshot(
    record: dict[str, object], request: OxaBookRequest
) -> OxaBookSnapshot:
    observed_symbol = _required_str(record, "symbol")
    if observed_symbol != request.symbol:
        raise ValueError(
            f"snapshot symbol {observed_symbol!r} does not match {request.symbol!r}"
        )
    timestamp = _required_str(record, "timestamp")
    ts_exchange_ms = _parse_timestamp_ms(timestamp)
    bounds = request.params()
    if not bounds["start"] <= ts_exchange_ms <= bounds["end"]:
        raise ValueError("snapshot timestamp is outside requested window")
    bids = _parse_levels(record.get("bids"), "bids", request.depth)
    asks = _parse_levels(record.get("asks"), "asks", request.depth)
    _validate_sorting(bids, asks)
    if Decimal(bids[0].px) >= Decimal(asks[0].px):
        raise ValueError("crossed or locked orderbook")
    return OxaBookSnapshot(
        symbol=observed_symbol,
        timestamp=timestamp,
        ts_exchange_ms=ts_exchange_ms,
        bids=bids,
        asks=asks,
    )


def _required_str(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"snapshot {field} must be a non-empty string")
    return value


def _parse_timestamp_ms(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid snapshot timestamp: {value!r}") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("snapshot timestamp must be UTC")
    return int(parsed.timestamp() * 1000)


def _parse_levels(value: object, side: str, depth: int) -> tuple[OxaLevel, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{side} orderbook side is empty")
    if len(value) > depth:
        raise ValueError(f"{side} depth exceeds requested depth {depth}")
    levels: list[OxaLevel] = []
    for raw_level in value:
        if not isinstance(raw_level, dict):
            raise ValueError(f"{side} level must be a JSON object")
        levels.append(_parse_level(raw_level, side))
    return tuple(levels)


def _parse_level(raw: dict[str, object], side: str) -> OxaLevel:
    px = raw.get("px")
    sz = raw.get("sz")
    count = raw.get("n")
    if not isinstance(px, str) or not isinstance(sz, str):
        raise ValueError(f"{side} price and size must be decimal strings")
    if _decimal(px, side) <= 0 or _decimal(sz, side) <= 0:
        raise ValueError(f"{side} price and size must be positive")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError(f"{side} order count must be a non-negative integer")
    return OxaLevel(px=px, sz=sz, n=count)


def _decimal(value: str, side: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{side} contains an invalid decimal") from exc
    if not number.is_finite():
        raise ValueError(f"{side} contains a non-finite decimal")
    return number


def _validate_sorting(bids: tuple[OxaLevel, ...], asks: tuple[OxaLevel, ...]) -> None:
    bid_prices = [Decimal(level.px) for level in bids]
    ask_prices = [Decimal(level.px) for level in asks]
    if any(left <= right for left, right in zip(bid_prices, bid_prices[1:])):
        raise ValueError("bids must be strictly descending")
    if any(left >= right for left, right in zip(ask_prices, ask_prices[1:])):
        raise ValueError("asks must be strictly ascending")
