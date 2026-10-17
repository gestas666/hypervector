"""Bounded 0xArchive liquidation-label acquisition for Hyperliquid core perps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from hypervector.data.oxa_api import (
    HttpSession,
    OxaRestClient,
    parse_utc_timestamp_ms,
    positive_decimal,
    validate_core_symbol,
    validate_window,
)
from hypervector.data.oxa_acquisition import (
    bundle_report,
    incomplete_fetch_error,
    partial_directory,
    reject_existing_partial,
    reusable_bundle_manifest,
)
from hypervector.data.oxa_pagination import paginate, write_raw_pages
from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    publish_immutable_directory,
    write_json,
)

_SOURCE = "0xarchive_hyperliquid_liquidations"
LIQUIDATION_NORMALIZATION_VERSION = "explicit_vendor_direction_v2"
_DIRECTION_SIDE = {
    "Close Long": ("long", "A"),
    "Close Short": ("short", "B"),
    "Liquidated Cross Long": ("long", "A"),
    "Liquidated Cross Short": ("short", "B"),
    "Liquidated Isolated Long": ("long", "A"),
    "Liquidated Isolated Short": ("short", "B"),
}


@dataclass(frozen=True)
class OxaLiquidationRequest:
    """Explicit bounds for one core-perp liquidation query."""

    symbol: str
    start: datetime
    end: datetime
    limit: int = 1000
    max_pages: int = 1
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        # Core perps only: HIP-3 liquidations live on a different vendor route
        # and identity, which this acquisition does not implement.
        validate_core_symbol(self.symbol)
        validate_window(self.start, self.end)
        if not 1 <= self.limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def params(self, cursor: str | None = None) -> dict[str, int | str]:
        """Build bounded query parameters without credential material."""
        values: dict[str, int | str] = {
            "start": int(self.start.timestamp() * 1000),
            "end": int(self.end.timestamp() * 1000),
            "limit": self.limit,
        }
        if cursor is not None:
            values["cursor"] = cursor
        return values


@dataclass(frozen=True)
class OxaLiquidationEvent:
    """One validated forced-liquidation fill from 0xArchive."""

    symbol: str
    timestamp: str
    ts_exchange_ms: int
    liquidated_user: str
    liquidator_user: str | None
    price: str
    size: str
    side: str
    mark_price: str | None
    closed_pnl: str | None
    direction: str
    trade_id: int | None
    tx_hash: str | None
    request_id: str | None

    @property
    def notional_usd(self) -> str:
        """Return exact price-times-size notional without float conversion."""
        return str(Decimal(self.price) * Decimal(self.size))

    @property
    def liquidated_direction(self) -> str:
        """Return the validated long or short position direction."""
        return _DIRECTION_SIDE[self.direction][0]

    @property
    def identity(self) -> tuple[object, ...]:
        """Return a stable vendor or source-derived event identity."""
        if self.trade_id is not None:
            return ("trade_id", self.trade_id)
        return (
            "source_fields_v1",
            self.timestamp,
            self.liquidated_user,
            self.liquidator_user,
            self.price,
            self.size,
            self.direction,
            self.tx_hash,
        )

    @property
    def content_signature(self) -> tuple[object, ...]:
        """Return economic event content excluding page request provenance."""
        return (
            self.symbol,
            self.timestamp,
            self.ts_exchange_ms,
            self.liquidated_user,
            self.liquidator_user,
            self.price,
            self.size,
            self.side,
            self.mark_price,
            self.closed_pnl,
            self.direction,
            self.trade_id,
            self.tx_hash,
        )

    def to_row(self) -> dict[str, object]:
        """Return one normalized, source-attributed liquidation label."""
        return {
            "ts_exchange_ms": self.ts_exchange_ms,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "liquidated_direction": self.liquidated_direction,
            "vendor_direction": self.direction,
            "exchange_side": self.side,
            "price": self.price,
            "size": self.size,
            "notional_usd": self.notional_usd,
            "mark_price": self.mark_price,
            "closed_pnl": self.closed_pnl,
            "liquidated_user": self.liquidated_user,
            "liquidator_user": self.liquidator_user,
            "trade_id": self.trade_id,
            "tx_hash": self.tx_hash,
            "vendor_request_id": self.request_id,
            "source": _SOURCE,
            "normalization_version": LIQUIDATION_NORMALIZATION_VERSION,
        }


@dataclass(frozen=True)
class OxaLiquidationPage:
    """One validated liquidation response page."""

    request_id: str | None
    next_cursor: str | None
    events: tuple[OxaLiquidationEvent, ...]
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class OxaLiquidationFetch:
    """Bounded liquidation pages and chronological normalized events."""

    pages: tuple[OxaLiquidationPage, ...]
    events: tuple[OxaLiquidationEvent, ...]
    complete: bool
    continuation_cursor: str | None

    @property
    def request_ids(self) -> tuple[str, ...]:
        """Return available vendor request identifiers in page order."""
        return tuple(
            page.request_id for page in self.pages if page.request_id is not None
        )


@dataclass(frozen=True)
class OxaStoredLiquidations:
    """Published raw pages, normalized labels, and manifest paths."""

    directory: Path
    events_path: Path
    manifest_path: Path


class OxaLiquidationClient:
    """Authenticated REST boundary for forced-liquidation history."""

    def __init__(
        self,
        *,
        api_key: str,
        session: HttpSession | None = None,
    ) -> None:
        self._client = OxaRestClient(api_key=api_key, session=session)

    def fetch_page(
        self,
        request: OxaLiquidationRequest,
        *,
        cursor: str | None = None,
    ) -> OxaLiquidationPage:
        """Fetch and validate one bounded liquidation page."""
        payload = self._client.get(
            f"/liquidations/{request.symbol}",
            params=request.params(cursor),
            timeout=request.timeout_seconds,
        )
        return parse_liquidation_page(payload, request)


def fetch_liquidation_history(
    client: OxaLiquidationClient,
    request: OxaLiquidationRequest,
) -> OxaLiquidationFetch:
    """Fetch bounded cursor pages and retain every validated event."""
    pages, cursor = paginate(
        lambda next_cursor: client.fetch_page(request, cursor=next_cursor),
        request.max_pages,
        label="liquidation",
    )
    events = _deduplicate_events(
        tuple(event for page in pages for event in page.events)
    )
    return OxaLiquidationFetch(pages, events, cursor is None, cursor)


def liquidation_output_directory(
    data_root: Path | str,
    request: OxaLiquidationRequest,
) -> Path:
    """Return the immutable directory for one liquidation window."""
    stamp = "%Y%m%dT%H%M%S%fZ"
    start, end = request.start.strftime(stamp), request.end.strftime(stamp)
    return (
        Path(data_root)
        / "cache"
        / "vendor"
        / "0xarchive"
        / "hyperliquid"
        / request.symbol
        / f"{start}_{end}_liquidations_v2"
    )


def store_liquidation_history(
    data_root: Path | str,
    request: OxaLiquidationRequest,
    result: OxaLiquidationFetch,
) -> OxaStoredLiquidations:
    """Atomically publish raw pages, normalized labels, and provenance."""
    return _publish_liquidations(
        liquidation_output_directory(data_root, request), request, result
    )


def _publish_liquidations(
    final: Path,
    request: OxaLiquidationRequest,
    result: OxaLiquidationFetch,
) -> OxaStoredLiquidations:
    def write_bundle(staging: Path) -> None:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        files = write_raw_pages(raw_dir, result.pages)
        events_path = staging / "liquidations.jsonl.gz"
        _write_event_rows(events_path, result.events)
        files[events_path.name] = file_evidence(events_path)
        write_json(staging / "manifest.json", _manifest(request, result, files))

    publish_immutable_directory(final, write_bundle)
    return OxaStoredLiquidations(
        final,
        final / "liquidations.jsonl.gz",
        final / "manifest.json",
    )


def acquire_and_store_liquidations(
    *,
    data_root: Path | str,
    api_key: str,
    request: OxaLiquidationRequest,
    session: HttpSession | None = None,
    allow_partial: bool = False,
) -> dict[str, object]:
    """Acquire one complete liquidation window and a secret-free report.

    An existing complete bundle is verified and reused with no vendor call; an
    unfinished cursor chain is never published at the canonical path.
    """
    directory = liquidation_output_directory(data_root, request)
    expected = {
        "source": _SOURCE,
        "normalization_version": LIQUIDATION_NORMALIZATION_VERSION,
        "symbol": request.symbol,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
    }
    if reusable_bundle_manifest(directory, kind="liquidation", expected=expected):
        return _report(request, directory, reused=True)
    if allow_partial:
        reject_existing_partial(directory, kind="liquidation")
    result = fetch_liquidation_history(
        OxaLiquidationClient(api_key=api_key, session=session), request
    )
    partial = not result.complete
    if partial and not allow_partial:
        raise incomplete_fetch_error(
            "liquidation",
            page_count=len(result.pages),
            continuation_cursor=result.continuation_cursor,
        )
    if partial:
        directory = partial_directory(directory)
    stored = _publish_liquidations(directory, request, result)
    return _report(request, stored.directory, reused=False, partial=partial)


def _report(
    request: OxaLiquidationRequest,
    directory: Path,
    *,
    reused: bool,
    partial: bool = False,
) -> dict[str, object]:
    return bundle_report(
        directory,
        identity={"source": _SOURCE, "venue": "hyperliquid", "symbol": request.symbol},
        path_key="liquidations_path",
        normalized_names=("liquidations.jsonl.gz",),
        counts=(
            "request_ids",
            "page_count",
            "event_count",
            "observed_start",
            "observed_end",
        ),
        reused=reused,
        partial=partial,
    )


def _write_event_rows(
    path: Path,
    events: tuple[OxaLiquidationEvent, ...],
) -> None:
    with gzip_text_writer(path) as handle:
        for event in events:
            row = event.to_row()
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def _manifest(
    request: OxaLiquidationRequest,
    result: OxaLiquidationFetch,
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    first = result.events[0].timestamp if result.events else None
    last = result.events[-1].timestamp if result.events else None
    return {
        "schema_version": 2,
        "normalization_version": LIQUIDATION_NORMALIZATION_VERSION,
        "source": _SOURCE,
        "source_api": "https://api.0xarchive.io/v1/hyperliquid/liquidations/{symbol}",
        "venue": "hyperliquid",
        "symbol": request.symbol,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "page_limit": request.limit,
        "max_pages": request.max_pages,
        "request_ids": list(result.request_ids),
        "page_count": len(result.pages),
        "event_count": len(result.events),
        "observed_start": first,
        "observed_end": last,
        "complete": result.complete,
        "continuation_cursor": result.continuation_cursor,
        "files": files,
    }


def _deduplicate_events(
    events: tuple[OxaLiquidationEvent, ...],
) -> tuple[OxaLiquidationEvent, ...]:
    unique: dict[tuple[object, ...], OxaLiquidationEvent] = {}
    for event in events:
        prior = unique.get(event.identity)
        if prior is not None and prior.content_signature != event.content_signature:
            raise ValueError("conflicting liquidation rows share one event identity")
        unique[event.identity] = event
    return tuple(
        sorted(
            unique.values(), key=lambda event: (event.ts_exchange_ms, event.identity)
        )
    )


def parse_liquidation_page(
    payload: object,
    request: OxaLiquidationRequest,
) -> OxaLiquidationPage:
    """Validate one live or persisted liquidation response page."""
    if not isinstance(payload, dict):
        raise ValueError("0xArchive response must be a JSON object")
    data, meta = payload.get("data"), payload.get("meta")
    if payload.get("success") is not True or not isinstance(data, list):
        raise ValueError("0xArchive response did not contain successful data")
    if not isinstance(meta, dict):
        raise ValueError("0xArchive liquidation response is missing meta")
    request_id = _optional_text(meta, "request_id")
    next_cursor = _optional_text(meta, "next_cursor")
    events = tuple(_parse_event(row, request, request_id) for row in data)
    return OxaLiquidationPage(request_id, next_cursor, events, payload)


def _parse_event(
    value: object,
    request: OxaLiquidationRequest,
    request_id: str | None,
) -> OxaLiquidationEvent:
    if not isinstance(value, dict):
        raise ValueError("0xArchive liquidation data must contain JSON objects")
    symbol = _text(value, "symbol")
    if symbol != request.symbol:
        raise ValueError(
            f"liquidation symbol {symbol!r} does not match {request.symbol!r}"
        )
    timestamp = _text(value, "timestamp")
    exchange_ms = parse_utc_timestamp_ms(timestamp, label="liquidation timestamp")
    bounds = request.params()
    if not bounds["start"] <= exchange_ms <= bounds["end"]:
        raise ValueError("liquidation timestamp is outside requested window")
    price, size = _text(value, "price"), _text(value, "size")
    positive_decimal(price, label="liquidation price")
    positive_decimal(size, label="liquidation size")
    side, direction = _text(value, "side"), _text(value, "direction")
    if side not in {"A", "B"}:
        raise ValueError("liquidation side must be A|B")
    if direction not in _DIRECTION_SIDE:
        raise ValueError("liquidation direction is unsupported")
    if side != _DIRECTION_SIDE[direction][1]:
        raise ValueError("liquidation direction and side disagree")
    return OxaLiquidationEvent(
        symbol=symbol,
        timestamp=timestamp,
        ts_exchange_ms=exchange_ms,
        liquidated_user=_text(value, "liquidated_user"),
        liquidator_user=_optional_empty_text(value, "liquidator_user"),
        price=price,
        size=size,
        side=side,
        mark_price=_optional_positive_decimal(value, "mark_price"),
        closed_pnl=_optional_decimal(value, "closed_pnl"),
        direction=direction,
        trade_id=_optional_nonnegative_integer(value, "trade_id"),
        tx_hash=_optional_text(value, "tx_hash"),
        request_id=request_id,
    )


def _text(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise ValueError(f"liquidation {field} must be a nonempty string")
    return item


def _optional_text(value: dict[str, object], field: str) -> str | None:
    item = value.get(field)
    if item is None:
        return None
    if not isinstance(item, str) or not item:
        raise ValueError(f"liquidation {field} must be a nonempty string or null")
    return item


def _optional_empty_text(value: dict[str, object], field: str) -> str | None:
    item = value.get(field)
    if item is None or item == "":
        return None
    if not isinstance(item, str):
        raise ValueError(f"liquidation {field} must be a string or null")
    return item


def _optional_positive_decimal(
    value: dict[str, object],
    field: str,
) -> str | None:
    item = _optional_text(value, field)
    if item is not None:
        positive_decimal(item, label=f"liquidation {field}")
    return item


def _optional_decimal(value: dict[str, object], field: str) -> str | None:
    item = _optional_text(value, field)
    if item is not None:
        try:
            number = Decimal(item)
        except InvalidOperation as exc:
            raise ValueError(
                f"liquidation {field} contains an invalid decimal"
            ) from exc
        if not number.is_finite():
            raise ValueError(f"liquidation {field} must be finite")
    return item


def _optional_nonnegative_integer(
    value: dict[str, object],
    field: str,
) -> int | None:
    item = value.get(field)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise ValueError(f"liquidation {field} must be a nonnegative integer or null")
    return item
