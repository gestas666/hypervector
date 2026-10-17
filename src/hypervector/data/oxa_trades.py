"""Bounded 0xArchive public-trade acquisition for Hyperliquid core markets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

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
    open_text_reader,
    publish_immutable_directory,
    write_json,
)

AggressorSide = Literal["buy", "sell"]
TradeIdSource = Literal["vendor", "derived_null_id_v1"]
TRADE_NORMALIZATION_VERSION = "taker_only_v2"
DEFAULT_TRADE_MAX_PAGES = 500
"""Shared resumable-backfill trade page bound per window (not part of identity)."""
_SOURCE = "0xarchive_hyperliquid_public_trades"
_SURROGATE_NAMESPACE = 1 << 62
_SURROGATE_MASK = _SURROGATE_NAMESPACE - 1


@dataclass(frozen=True)
class OxaTradeRequest:
    """Explicit bounds for Hyperliquid participant-fill history."""

    symbol: str
    start: datetime
    end: datetime
    limit: int = 1000
    max_pages: int = 1
    timeout_seconds: float = 30.0
    market_family: MarketFamily = "core"

    def __post_init__(self) -> None:
        validate_market_symbol(self.symbol, self.market_family)
        validate_window(self.start, self.end)
        if not 1 <= self.limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def params(self, cursor: str | None = None) -> dict[str, int | str]:
        """Build bounded query parameters without credentials."""
        values: dict[str, int | str] = {
            "start": int(self.start.timestamp() * 1000),
            "end": int(self.end.timestamp() * 1000),
            "limit": self.limit,
        }
        if cursor is not None:
            values["cursor"] = cursor
        return values


@dataclass(frozen=True)
class OxaParticipantFill:
    """Validated maker- or taker-side fill returned by the vendor API."""

    symbol: str
    side: str
    price: str
    size: str
    timestamp: str
    ts_exchange_ms: int
    trade_id: int | None
    crossed: bool | None
    request_id: str
    tx_hash: str | None
    order_id: int | None
    user_address: str | None

    @property
    def market_signature(self) -> tuple[object, ...]:
        """Return fields that must agree across both sides of one match."""
        return (
            self.symbol,
            self.price,
            self.size,
            self.timestamp,
            self.ts_exchange_ms,
            self.trade_id,
        )


@dataclass(frozen=True)
class OxaPublicTrade:
    """One public match normalized from participant-side fills."""

    symbol: str
    aggressor_side: AggressorSide
    price: str
    size: str
    timestamp: str
    ts_exchange_ms: int
    trade_id: int
    request_id: str
    trade_id_source: TradeIdSource

    def to_replay_row(self) -> dict[str, object]:
        """Return replay JSON without participant costs or receive time."""
        return {
            "ts_exchange_ms": self.ts_exchange_ms,
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "aggressor_side": self.aggressor_side,
            "price": self.price,
            "size": self.size,
            "vendor_request_id": self.request_id,
            "trade_id_source": self.trade_id_source,
            "source": "0xarchive_hyperliquid_public_trades",
        }


@dataclass(frozen=True)
class OxaTradePage:
    """One validated participant-fill response envelope."""

    request_id: str
    next_cursor: str | None
    fills: tuple[OxaParticipantFill, ...]
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class OxaTradeFetch:
    """Bounded trade pages and one-match normalized public prints."""

    pages: tuple[OxaTradePage, ...]
    trades: tuple[OxaPublicTrade, ...]
    complete: bool
    continuation_cursor: str | None
    unresolved_fill_groups: int

    @property
    def request_ids(self) -> tuple[str, ...]:
        """Return vendor correlation identifiers in request order."""
        return tuple(page.request_id for page in self.pages)


@dataclass(frozen=True)
class OxaStoredTrades:
    """Published participant evidence and normalized public-trade paths."""

    directory: Path
    trades_path: Path
    manifest_path: Path


class OxaTradeClient:
    """Authenticated REST boundary for participant-fill history."""

    def __init__(
        self,
        *,
        api_key: str,
        session: HttpSession | None = None,
    ) -> None:
        self._client = OxaRestClient(api_key=api_key, session=session)

    def fetch_page(
        self,
        request: OxaTradeRequest,
        *,
        cursor: str | None = None,
    ) -> OxaTradePage:
        """Fetch and validate one bounded participant-fill page."""
        payload = self._client.get(
            _trade_route(request),
            params=request.params(cursor),
            timeout=request.timeout_seconds,
        )
        return parse_trade_page(payload, request)


def fetch_trade_history(
    client: OxaTradeClient,
    request: OxaTradeRequest,
) -> OxaTradeFetch:
    """Fetch bounded pages and normalize one public print per match."""
    pages, _cursor = paginate(
        lambda next_cursor: client.fetch_page(request, cursor=next_cursor),
        request.max_pages,
        label="trade",
    )
    return normalize_trade_pages(pages)


def normalize_trade_pages(
    pages: tuple[OxaTradePage, ...],
) -> OxaTradeFetch:
    """Normalize validated stored or freshly fetched participant pages."""
    if not pages:
        raise ValueError("at least one trade page is required")
    cursor = pages[-1].next_cursor
    trades, unresolved = _normalize_fills(list(pages), incomplete=cursor is not None)
    return OxaTradeFetch(
        pages=pages,
        trades=trades,
        complete=cursor is None,
        continuation_cursor=cursor,
        unresolved_fill_groups=unresolved,
    )


def trade_output_directory(
    data_root: Path | str,
    request: OxaTradeRequest,
) -> Path:
    """Return the immutable directory for one requested trade window."""
    stamp = "%Y%m%dT%H%M%S%fZ"
    start, end = request.start.strftime(stamp), request.end.strftime(stamp)
    return (
        Path(data_root)
        / "cache"
        / "vendor"
        / "0xarchive"
        / "hyperliquid"
        / request.symbol
        / f"{start}_{end}_trades"
    )


def store_trade_history(
    data_root: Path | str,
    request: OxaTradeRequest,
    result: OxaTradeFetch,
) -> OxaStoredTrades:
    """Atomically publish raw fills, normalized trades, and their manifest."""
    return _publish_trades(trade_output_directory(data_root, request), request, result)


def _publish_trades(
    final: Path,
    request: OxaTradeRequest,
    result: OxaTradeFetch,
) -> OxaStoredTrades:
    def write_bundle(staging: Path) -> None:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        files = write_raw_pages(raw_dir, result.pages)
        trades_path = staging / "trades.jsonl.gz"
        write_trade_jsonl(trades_path, result.trades)
        files["trades.jsonl.gz"] = file_evidence(trades_path)
        write_json(staging / "manifest.json", _manifest(request, result, files))

    publish_immutable_directory(final, write_bundle)
    return OxaStoredTrades(final, final / "trades.jsonl.gz", final / "manifest.json")


def acquire_and_store_trades(
    *,
    data_root: Path | str,
    api_key: str,
    request: OxaTradeRequest,
    session: HttpSession | None = None,
    allow_partial: bool = False,
) -> dict[str, object]:
    """Acquire one complete participant-fill window and a secret-free report.

    An existing complete bundle is verified and reused with no vendor call; an
    unfinished cursor chain is never published at the canonical path.
    """
    directory = trade_output_directory(data_root, request)
    if reusable_bundle_manifest(
        directory, kind="trade", expected=_reuse_identity(request)
    ):
        return _report(request, directory, reused=True)
    if allow_partial:
        reject_existing_partial(directory, kind="trade")
    result = fetch_trade_history(
        OxaTradeClient(api_key=api_key, session=session), request
    )
    partial = not result.complete
    if partial and not allow_partial:
        raise incomplete_fetch_error(
            "trade",
            page_count=len(result.pages),
            continuation_cursor=result.continuation_cursor,
        )
    if not partial and result.unresolved_fill_groups:
        raise ValueError(
            f"trade participant groups unresolved ({result.unresolved_fill_groups}); "
            "nothing was stored"
        )
    if partial:
        directory = partial_directory(directory)
    stored = _publish_trades(directory, request, result)
    return _report(request, stored.directory, reused=False, partial=partial)


def _reuse_identity(request: OxaTradeRequest) -> dict[str, object]:
    identity: dict[str, object] = {
        "source": _SOURCE,
        "symbol": request.symbol,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "normalization_version": TRADE_NORMALIZATION_VERSION,
    }
    if request.market_family == "hip3":
        identity["market_family"] = "hip3"
    return identity


def _report(
    request: OxaTradeRequest,
    directory: Path,
    *,
    reused: bool,
    partial: bool = False,
) -> dict[str, object]:
    return bundle_report(
        directory,
        identity={
            "source": _SOURCE,
            "venue": "hyperliquid",
            "market_family": request.market_family,
            "symbol": request.symbol,
        },
        path_key="trades_path",
        normalized_names=("trades.jsonl.gz", "trades.jsonl"),
        counts=(
            "request_ids",
            "page_count",
            "raw_fill_count",
            "trade_count",
            "normalization_version",
            "surrogate_trade_id_count",
            "unresolved_fill_groups",
            "observed_start",
            "observed_end",
        ),
        reused=reused,
        partial=partial,
    )


def load_trade_jsonl(path: Path | str) -> pd.DataFrame:
    """Load normalized public trades into a validated chronological frame."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"trade JSONL file not found: {source}")
    with open_text_reader(source) as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    frame = pd.DataFrame(rows)
    required = {"ts_exchange_ms", "trade_id", "aggressor_side", "price", "size"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"trade JSONL missing columns: {sorted(missing)}")
    frame = frame.rename(columns={"ts_exchange_ms": "ts_ms"})
    frame["price"] = pd.to_numeric(frame["price"], errors="raise")
    frame["size"] = pd.to_numeric(frame["size"], errors="raise")
    if not frame["aggressor_side"].isin(("buy", "sell")).all():
        raise ValueError("trade JSONL aggressor_side must be buy|sell")
    return frame.sort_values(["ts_ms", "trade_id"]).reset_index(drop=True)


def write_trade_jsonl(path: Path, trades: tuple[OxaPublicTrade, ...]) -> None:
    """Write normalized public taker trades as deterministic gzip JSONL."""
    with gzip_text_writer(path) as handle:
        for trade in trades:
            row = trade.to_replay_row()
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def _manifest(
    request: OxaTradeRequest,
    result: OxaTradeFetch,
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    first = result.trades[0].timestamp if result.trades else None
    last = result.trades[-1].timestamp if result.trades else None
    return {
        "schema_version": 1,
        "source": "0xarchive_hyperliquid_public_trades",
        "source_api": f"{API_ROOT}{_trade_route(request, symbol='{symbol}')}",
        "venue": "hyperliquid",
        "market_family": request.market_family,
        "symbol": request.symbol,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "page_limit": request.limit,
        "max_pages": request.max_pages,
        "request_ids": list(result.request_ids),
        "page_count": len(result.pages),
        "raw_fill_count": sum(len(page.fills) for page in result.pages),
        "trade_count": len(result.trades),
        "normalization_version": TRADE_NORMALIZATION_VERSION,
        "surrogate_trade_id_count": _surrogate_count(result.trades),
        "unresolved_fill_groups": result.unresolved_fill_groups,
        "observed_start": first,
        "observed_end": last,
        "complete": result.complete,
        "continuation_cursor": result.continuation_cursor,
        "files": files,
    }


def _trade_route(request: OxaTradeRequest, *, symbol: str | None = None) -> str:
    """Return the route-family-correct participant-fill endpoint."""
    prefix = "/hip3" if request.market_family == "hip3" else ""
    return f"{prefix}/trades/{symbol or request.symbol}"


def parse_trade_page(payload: object, request: OxaTradeRequest) -> OxaTradePage:
    """Validate one persisted or live 0xArchive trade response page."""
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
    fills = tuple(_parse_fill(row, request, request_id) for row in data)
    return OxaTradePage(request_id, next_cursor, fills, payload)


def _parse_fill(
    value: object,
    request: OxaTradeRequest,
    request_id: str,
) -> OxaParticipantFill:
    if not isinstance(value, dict):
        raise ValueError("0xArchive trade data must contain JSON objects")
    symbol = _text(value, "symbol")
    if symbol != request.symbol:
        raise ValueError(f"trade symbol {symbol!r} does not match {request.symbol!r}")
    side = _text(value, "side")
    if side not in {"A", "B"}:
        raise ValueError("trade side must be A|B")
    price, size = _text(value, "price"), _text(value, "size")
    positive_decimal(price, label="trade price")
    positive_decimal(size, label="trade size")
    timestamp = _text(value, "timestamp")
    exchange_ms = parse_utc_timestamp_ms(timestamp, label="trade timestamp")
    bounds = request.params()
    if not bounds["start"] <= exchange_ms <= bounds["end"]:
        raise ValueError("trade timestamp is outside requested window")
    trade_id = _trade_id(value.get("trade_id"))
    crossed = value.get("crossed")
    if crossed is not None and not isinstance(crossed, bool):
        raise ValueError("trade crossed must be boolean or null")
    return OxaParticipantFill(
        symbol,
        side,
        price,
        size,
        timestamp,
        exchange_ms,
        trade_id,
        crossed,
        request_id,
        _optional_text(value, "tx_hash"),
        _optional_integer(value, "order_id"),
        _optional_text(value, "user_address"),
    )


def _normalize_fills(
    pages: list[OxaTradePage],
    *,
    incomplete: bool,
) -> tuple[tuple[OxaPublicTrade, ...], int]:
    groups: dict[int, list[OxaParticipantFill]] = {}
    legacy: list[OxaParticipantFill] = []
    for page in pages:
        for fill in page.fills:
            if fill.trade_id is None:
                legacy.append(fill)
            else:
                groups.setdefault(fill.trade_id, []).append(fill)
    trades: list[OxaPublicTrade] = []
    unresolved = 0
    for fills in groups.values():
        selected = _select_participant(fills)
        if selected is None:
            unresolved += int(incomplete)
        else:
            trades.append(_native_public_trade(selected))
    legacy_trades, legacy_unresolved = _normalize_legacy_null_ids(legacy)
    trades.extend(legacy_trades)
    unresolved += legacy_unresolved
    trades.sort(key=lambda trade: (trade.ts_exchange_ms, trade.trade_id))
    return tuple(trades), unresolved


def _normalize_legacy_null_ids(
    fills: list[OxaParticipantFill],
) -> tuple[tuple[OxaPublicTrade, ...], int]:
    if not fills:
        return (), 0
    takers = [fill for fill in fills if fill.crossed is True]
    if not takers:
        return (), 0
    for fill in takers:
        _validate_surrogate_provenance(fill)
    unique = {_legacy_identity(fill): fill for fill in takers}
    takers = sorted(unique.values(), key=_legacy_identity)
    trades = tuple(
        _public_trade(
            fill,
            trade_id=_surrogate_trade_id(fill),
            trade_id_source="derived_null_id_v1",
        )
        for fill in takers
    )
    if len({trade.trade_id for trade in trades}) != len(trades):
        raise ValueError("legacy null trade IDs produced a surrogate collision")
    return trades, 0


def _select_participant(
    fills: list[OxaParticipantFill],
) -> OxaParticipantFill | None:
    if len({fill.market_signature for fill in fills}) != 1:
        raise ValueError("conflicting participant fills for one trade_id")
    takers = [fill for fill in fills if fill.crossed is True]
    if takers:
        if len({fill.side for fill in takers}) != 1:
            raise ValueError("conflicting taker fills for one trade_id")
        return takers[0]
    if len(fills) == 1 and fills[0].crossed is None:
        return fills[0]
    if all(fill.crossed is False for fill in fills):
        return None
    raise ValueError("trade_id has no participant with an inferable aggressor side")


def _native_public_trade(fill: OxaParticipantFill) -> OxaPublicTrade:
    if fill.trade_id is None:
        raise ValueError("native public trade requires a vendor trade_id")
    return _public_trade(fill, trade_id=fill.trade_id, trade_id_source="vendor")


def _public_trade(
    fill: OxaParticipantFill,
    *,
    trade_id: int,
    trade_id_source: TradeIdSource,
) -> OxaPublicTrade:
    if fill.crossed is False:
        raise ValueError("maker participant fill cannot become a public taker trade")
    aggressor: AggressorSide = "buy" if fill.side == "B" else "sell"
    return OxaPublicTrade(
        fill.symbol,
        aggressor,
        fill.price,
        fill.size,
        fill.timestamp,
        fill.ts_exchange_ms,
        trade_id,
        fill.request_id,
        trade_id_source,
    )


def _validate_surrogate_provenance(fill: OxaParticipantFill) -> None:
    """Reject null-ID takers that cannot receive a repeatable identity."""
    if fill.tx_hash is None or fill.order_id is None or fill.user_address is None:
        raise ValueError("legacy null-ID taker lacks stable order provenance")


def _surrogate_trade_id(fill: OxaParticipantFill) -> int:
    _validate_surrogate_provenance(fill)
    identity = _legacy_identity(fill)
    encoded = json.dumps(identity, separators=(",", ":")).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big")
    return _SURROGATE_NAMESPACE | (value & _SURROGATE_MASK)


def _legacy_identity(fill: OxaParticipantFill) -> tuple[object, ...]:
    return (
        "oxa_null_trade_id_v1",
        fill.symbol,
        fill.timestamp,
        fill.ts_exchange_ms,
        fill.price,
        fill.size,
        fill.side,
        fill.crossed,
        fill.tx_hash,
        fill.order_id,
        fill.user_address,
    )


def _surrogate_count(trades: tuple[OxaPublicTrade, ...]) -> int:
    return sum(trade.trade_id_source == "derived_null_id_v1" for trade in trades)


def _text(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"trade {key} must be a non-empty string")
    return value


def _trade_id(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("trade_id must be null or a non-negative integer")
    return value


def _optional_text(values: dict[str, object], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"trade {key} must be null or a non-empty string")
    return value


def _optional_integer(values: dict[str, object], key: str) -> int | None:
    value = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"trade {key} must be null or a non-negative integer")
    return value
