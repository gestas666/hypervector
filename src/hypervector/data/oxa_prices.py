"""Immutable Hyperliquid mark/oracle price acquisition from 0xArchive."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_api import (
    API_ROOT,
    HttpSession,
    MarketFamily,
    OxaRestClient,
    parse_utc_timestamp_ms,
    positive_decimal,
    validate_market_symbol,
    validate_window,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_gzip_json,
    write_json,
)

_SOURCE = "0xarchive_hyperliquid_prices"


@dataclass(frozen=True)
class OxaPriceRequest:
    """Explicit bounds for one Hyperliquid price-history request."""

    symbol: str
    start: datetime
    end: datetime
    limit: int = 1000
    max_pages: int = 200
    timeout_seconds: float = 30.0
    market_family: MarketFamily = "core"

    def __post_init__(self) -> None:
        validate_market_symbol(self.symbol, self.market_family)
        validate_window(self.start, self.end)
        if not 1 <= self.limit <= 1000:
            raise ValueError("price limit must be between 1 and 1000")
        if self.max_pages < 1 or self.timeout_seconds <= 0.0:
            raise ValueError("price max_pages and timeout must be positive")

    def params(self, cursor: str | None = None) -> dict[str, int | str]:
        """Build bounded query parameters without credential material."""
        params: dict[str, int | str] = {
            "start": int(self.start.timestamp() * 1000),
            "end": int(self.end.timestamp() * 1000),
            "limit": self.limit,
        }
        if cursor is not None:
            params["cursor"] = cursor
        return params


@dataclass(frozen=True)
class OxaPriceSnapshot:
    """One decimal-safe venue price context observation."""

    timestamp: str
    ts_ms: int
    mark_price: str | None
    oracle_price: str | None
    mid_price: str | None

    def to_row(self) -> dict[str, object]:
        """Return one normalized record with explicit source identity."""
        return {**asdict(self), "source": _SOURCE}


@dataclass(frozen=True)
class OxaPricePage:
    """One validated vendor price response envelope."""

    request_id: str
    next_cursor: str | None
    snapshots: tuple[OxaPriceSnapshot, ...]
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class OxaPriceFetch:
    """Bounded price pages and normalized unique observations."""

    pages: tuple[OxaPricePage, ...]
    snapshots: tuple[OxaPriceSnapshot, ...]
    complete: bool
    continuation_cursor: str | None

    @property
    def request_ids(self) -> tuple[str, ...]:
        """Return vendor request identifiers in page order."""
        return tuple(page.request_id for page in self.pages)


@dataclass(frozen=True)
class OxaStoredPrices:
    """Published price evidence and manifest paths."""

    directory: Path
    prices_path: Path
    manifest_path: Path


class OxaPriceClient:
    """Authenticated boundary for Hyperliquid price history."""

    def __init__(self, *, api_key: str, session: HttpSession | None = None) -> None:
        self._client = OxaRestClient(api_key=api_key, session=session)

    def fetch_page(
        self, request: OxaPriceRequest, *, cursor: str | None = None
    ) -> OxaPricePage:
        """Fetch and validate one price-history page."""
        payload = self._client.get(
            _price_route(request),
            params=request.params(cursor),
            timeout=request.timeout_seconds,
        )
        return _parse_page(payload, request)


def fetch_price_history(
    client: OxaPriceClient, request: OxaPriceRequest
) -> OxaPriceFetch:
    """Fetch bounded pages and reject conflicting cursor-boundary rows."""
    pages: list[OxaPricePage] = []
    cursor: str | None = None
    for _ in range(request.max_pages):
        page = client.fetch_page(request, cursor=cursor)
        pages.append(page)
        next_cursor = page.next_cursor
        if next_cursor is None:
            cursor = None
            break
        if next_cursor == cursor:
            raise ValueError("0xArchive price cursor did not advance")
        cursor = next_cursor
    snapshots = _merge_snapshots(pages, int(request.end.timestamp() * 1000))
    return OxaPriceFetch(tuple(pages), snapshots, cursor is None, cursor)


def price_output_directory(data_root: Path | str, request: OxaPriceRequest) -> Path:
    """Return the immutable directory for one price-history window."""
    stamp = "%Y%m%dT%H%M%S%fZ"
    window = f"{request.start.strftime(stamp)}_{request.end.strftime(stamp)}"
    return (
        Path(data_root)
        / "cache"
        / "vendor"
        / "0xarchive"
        / "hyperliquid"
        / request.symbol
        / f"{window}_prices"
    )


def store_price_history(
    data_root: Path | str,
    request: OxaPriceRequest,
    result: OxaPriceFetch,
) -> OxaStoredPrices:
    """Atomically publish raw pages, normalized Parquet, and a manifest."""
    final = price_output_directory(data_root, request)

    def write_bundle(staging: Path) -> None:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        files = _write_raw_pages(raw_dir, result.pages)
        prices_path = staging / "prices.parquet"
        pd.DataFrame(row.to_row() for row in result.snapshots).to_parquet(
            prices_path, index=False
        )
        files["prices.parquet"] = file_evidence(prices_path)
        write_json(staging / "manifest.json", _manifest(request, result, files))

    publish_immutable_directory(final, write_bundle)
    return OxaStoredPrices(final, final / "prices.parquet", final / "manifest.json")


def acquire_and_store_prices(
    *, data_root: Path | str, api_key: str, request: OxaPriceRequest
) -> dict[str, object]:
    """Acquire a complete price window and return a secret-free report."""
    result = fetch_price_history(OxaPriceClient(api_key=api_key), request)
    if not result.complete:
        raise ValueError("price max-pages exhausted before completing the window")
    stored = store_price_history(data_root, request, result)
    return {
        "ok": True,
        "venue": "hyperliquid",
        "source": _SOURCE,
        "symbol": request.symbol,
        "row_count": len(result.snapshots),
        "page_count": len(result.pages),
        "request_ids": list(result.request_ids),
        "complete": result.complete,
        "directory": str(stored.directory.resolve()),
        "prices_path": str(stored.prices_path.resolve()),
        "manifest_path": str(stored.manifest_path.resolve()),
    }


def _parse_page(payload: object, request: OxaPriceRequest) -> OxaPricePage:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("0xArchive price response must be a successful object")
    data, meta = payload.get("data"), payload.get("meta")
    if not isinstance(data, list) or not isinstance(meta, dict):
        raise ValueError("0xArchive price response is missing data or meta")
    request_id, cursor = meta.get("request_id"), meta.get("next_cursor")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("0xArchive price response is missing request_id")
    if cursor is not None and not isinstance(cursor, str):
        raise ValueError("0xArchive price cursor must be a string or null")
    snapshots = tuple(_parse_snapshot(row, request) for row in data)
    return OxaPricePage(request_id, cursor, snapshots, payload)


def _parse_snapshot(value: object, request: OxaPriceRequest) -> OxaPriceSnapshot:
    if not isinstance(value, dict):
        raise ValueError("0xArchive price data must contain objects")
    timestamp = value.get("timestamp")
    if not isinstance(timestamp, str):
        raise ValueError("price timestamp must be a string")
    ts_ms = parse_utc_timestamp_ms(timestamp, label="price timestamp")
    bounds = request.params()
    if not bounds["start"] <= ts_ms <= bounds["end"]:
        raise ValueError("price timestamp is outside requested window")
    return OxaPriceSnapshot(
        timestamp,
        ts_ms,
        _decimal_text(value.get("mark_price"), "mark_price"),
        _decimal_text(value.get("oracle_price"), "oracle_price"),
        _decimal_text(value.get("mid_price"), "mid_price"),
    )


def _decimal_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"price {label} must be a decimal string or null")
    positive_decimal(value, label=f"price {label}")
    return value


def _merge_snapshots(
    pages: list[OxaPricePage], end_ms: int
) -> tuple[OxaPriceSnapshot, ...]:
    merged: dict[int, OxaPriceSnapshot] = {}
    for page in pages:
        for snapshot in page.snapshots:
            if snapshot.ts_ms == end_ms:
                continue
            existing = merged.get(snapshot.ts_ms)
            if existing is not None and existing != snapshot:
                raise ValueError("conflicting duplicate price timestamp")
            merged[snapshot.ts_ms] = snapshot
    return tuple(merged[key] for key in sorted(merged))


def _write_raw_pages(
    raw_dir: Path, pages: tuple[OxaPricePage, ...]
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    for index, page in enumerate(pages, start=1):
        path = raw_dir / f"page-{index:04d}.json.gz"
        write_gzip_json(path, page.raw_payload)
        evidence[f"raw/{path.name}"] = file_evidence(path)
    return evidence


def _manifest(
    request: OxaPriceRequest,
    result: OxaPriceFetch,
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": _SOURCE,
        "source_api": f"{API_ROOT}{_price_route(request, symbol='{symbol}')}",
        "venue": "hyperliquid",
        "market_family": request.market_family,
        "symbol": request.symbol,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "page_limit": request.limit,
        "max_pages": request.max_pages,
        "request_ids": list(result.request_ids),
        "page_count": len(result.pages),
        "row_count": len(result.snapshots),
        "complete": result.complete,
        "continuation_cursor": result.continuation_cursor,
        "files": files,
    }


def _price_route(request: OxaPriceRequest, *, symbol: str | None = None) -> str:
    """Return the route-family-correct price-history endpoint."""
    prefix = "/hip3" if request.market_family == "hip3" else ""
    return f"{prefix}/prices/{symbol or request.symbol}"
