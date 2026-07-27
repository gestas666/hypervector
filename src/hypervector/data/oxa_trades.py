"""Bounded 0xArchive public-trade acquisition for Hyperliquid core markets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from hypervector.data.oxa_api import (
    API_ROOT,
    HttpSession,
    OxaRestClient,
    parse_utc_timestamp_ms,
    positive_decimal,
    validate_symbol,
    validate_window,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    open_text_reader,
    publish_immutable_directory,
    write_gzip_json,
    write_json,
)

AggressorSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class OxaTradeRequest:
    """Explicit bounds for Hyperliquid participant-fill history."""

    symbol: str
    start: datetime
    end: datetime
    limit: int = 1000
    max_pages: int = 1
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
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
    trade_id: int
    crossed: bool | None
    request_id: str

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
            f"/trades/{request.symbol}",
            params=request.params(cursor),
            timeout=request.timeout_seconds,
        )
        return _parse_page(payload, request)


def fetch_trade_history(
    client: OxaTradeClient,
    request: OxaTradeRequest,
) -> OxaTradeFetch:
    """Fetch bounded pages and normalize one public print per match."""
    pages: list[OxaTradePage] = []
    cursor: str | None = None
    for _ in range(request.max_pages):
        page = client.fetch_page(request, cursor=cursor)
        pages.append(page)
        cursor = page.next_cursor
        if cursor is None:
            break
    trades, unresolved = _normalize_fills(pages, incomplete=cursor is not None)
    return OxaTradeFetch(
        pages=tuple(pages),
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
    final = trade_output_directory(data_root, request)

    def write_bundle(staging: Path) -> None:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        files = _write_raw_pages(raw_dir, result.pages)
        trades_path = staging / "trades.jsonl.gz"
        _write_trades(trades_path, result.trades)
        files["trades.jsonl.gz"] = file_evidence(trades_path)
        write_json(staging / "manifest.json", _manifest(request, result, files))

    publish_immutable_directory(final, write_bundle)
    return OxaStoredTrades(final, final / "trades.jsonl.gz", final / "manifest.json")


def acquire_and_store_trades(
    *,
    data_root: Path | str,
    api_key: str,
    request: OxaTradeRequest,
) -> dict[str, object]:
    """Acquire bounded participant fills and return a secret-free report."""
    result = fetch_trade_history(OxaTradeClient(api_key=api_key), request)
    stored = store_trade_history(data_root, request, result)
    first = result.trades[0].timestamp if result.trades else None
    last = result.trades[-1].timestamp if result.trades else None
    return {
        "ok": True,
        "source": "0xarchive_hyperliquid_public_trades",
        "venue": "hyperliquid",
        "symbol": request.symbol,
        "directory": str(stored.directory.resolve()),
        "trades_path": str(stored.trades_path.resolve()),
        "manifest_path": str(stored.manifest_path.resolve()),
        "request_ids": list(result.request_ids),
        "page_count": len(result.pages),
        "raw_fill_count": sum(len(page.fills) for page in result.pages),
        "trade_count": len(result.trades),
        "unresolved_fill_groups": result.unresolved_fill_groups,
        "observed_start": first,
        "observed_end": last,
        "complete": result.complete,
        "continuation_cursor": result.continuation_cursor,
    }


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


def _write_raw_pages(
    raw_dir: Path,
    pages: tuple[OxaTradePage, ...],
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    for index, page in enumerate(pages, start=1):
        path = raw_dir / f"page-{index:04d}.json.gz"
        write_gzip_json(path, page.raw_payload)
        evidence[f"raw/{path.name}"] = file_evidence(path)
    return evidence


def _write_trades(path: Path, trades: tuple[OxaPublicTrade, ...]) -> None:
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
        "source_api": f"{API_ROOT}/trades/{{symbol}}",
        "venue": "hyperliquid",
        "symbol": request.symbol,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "page_limit": request.limit,
        "max_pages": request.max_pages,
        "request_ids": list(result.request_ids),
        "page_count": len(result.pages),
        "raw_fill_count": sum(len(page.fills) for page in result.pages),
        "trade_count": len(result.trades),
        "unresolved_fill_groups": result.unresolved_fill_groups,
        "observed_start": first,
        "observed_end": last,
        "complete": result.complete,
        "continuation_cursor": result.continuation_cursor,
        "files": files,
    }


def _parse_page(payload: object, request: OxaTradeRequest) -> OxaTradePage:
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
        symbol, side, price, size, timestamp, exchange_ms, trade_id, crossed, request_id
    )


def _normalize_fills(
    pages: list[OxaTradePage],
    *,
    incomplete: bool,
) -> tuple[tuple[OxaPublicTrade, ...], int]:
    groups: dict[int, list[OxaParticipantFill]] = {}
    for page in pages:
        for fill in page.fills:
            groups.setdefault(fill.trade_id, []).append(fill)
    trades: list[OxaPublicTrade] = []
    unresolved = 0
    for fills in groups.values():
        selected = _select_taker(fills, incomplete=incomplete)
        if selected is None:
            unresolved += 1
        else:
            trades.append(_public_trade(selected))
    trades.sort(key=lambda trade: (trade.ts_exchange_ms, trade.trade_id))
    return tuple(trades), unresolved


def _select_taker(
    fills: list[OxaParticipantFill],
    *,
    incomplete: bool,
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
    if incomplete:
        return None
    raise ValueError("trade_id has no unambiguous taker fill")


def _public_trade(fill: OxaParticipantFill) -> OxaPublicTrade:
    aggressor: AggressorSide = "buy" if fill.side == "B" else "sell"
    return OxaPublicTrade(
        fill.symbol,
        aggressor,
        fill.price,
        fill.size,
        fill.timestamp,
        fill.ts_exchange_ms,
        fill.trade_id,
        fill.request_id,
    )


def _text(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"trade {key} must be a non-empty string")
    return value


def _trade_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("trade_id must be a non-negative integer")
    return value
