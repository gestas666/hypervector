"""Validated public Hyperliquid L2 snapshot and trade event models."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal, Mapping, cast

AggressorSide = Literal["buy", "sell"]
TimestampSource = Literal["local_receive_no_exchange_timestamp"]


@dataclass(frozen=True)
class BookLevel:
    """One price-aggregated Hyperliquid L2 level."""

    price: float
    size: float
    order_count: int

    def __post_init__(self) -> None:
        _positive(self.price, "price")
        _positive(self.size, "size")
        if isinstance(self.order_count, bool) or self.order_count < 0:
            raise ValueError("order_count must be a non-negative integer")


@dataclass(frozen=True)
class L2SnapshotEvent:
    """One complete public L2 snapshot with exchange and receipt timestamps."""

    symbol: str
    exchange_ts_ms: int
    received_ts_ns: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    source: str = "hyperliquid_ws_l2Book"

    def __post_init__(self) -> None:
        _nonempty(self.symbol, "symbol")
        _positive_integer(self.exchange_ts_ms, "exchange_ts_ms")
        _positive_integer(self.received_ts_ns, "received_ts_ns")
        if not self.bids or not self.asks:
            raise ValueError("L2 snapshot requires bids and asks")

    @property
    def utc_date(self) -> str:
        """Return the exchange event's UTC calendar date."""
        return _utc_date_ms(self.exchange_ts_ms)

    @property
    def event_key(self) -> str:
        """Return a stable identity for exact snapshot deduplication."""
        identity = {
            "symbol": self.symbol,
            "exchange_ts_ms": self.exchange_ts_ms,
            "bids": [asdict(level) for level in self.bids],
            "asks": [asdict(level) for level in self.asks],
            "source": self.source,
        }
        payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PublicTradeEvent:
    """One public Hyperliquid match from the trades channel."""

    symbol: str
    aggressor_side: AggressorSide
    price: float
    size: float
    transaction_hash: str
    exchange_ts_ms: int
    received_ts_ns: int
    trade_id: int
    buyer: str
    seller: str
    source: str = "hyperliquid_ws_trades"

    def __post_init__(self) -> None:
        _nonempty(self.symbol, "symbol")
        if self.aggressor_side not in {"buy", "sell"}:
            raise ValueError("aggressor_side must be buy|sell")
        _positive(self.price, "price")
        _positive(self.size, "size")
        _nonempty(self.transaction_hash, "transaction_hash")
        _positive_integer(self.exchange_ts_ms, "exchange_ts_ms")
        _positive_integer(self.received_ts_ns, "received_ts_ns")
        _nonnegative_integer(self.trade_id, "trade_id")
        _nonempty(self.buyer, "buyer")
        _nonempty(self.seller, "seller")

    @property
    def utc_date(self) -> str:
        """Return the exchange event's UTC calendar date."""
        return _utc_date_ms(self.exchange_ts_ms)

    @property
    def trade_key(self) -> str:
        """Return Hyperliquid's documented globally unique trade identity."""
        return f"{self.exchange_ts_ms}:{self.symbol}:{self.trade_id}"


@dataclass(frozen=True)
class AssetContextEvent:
    """One public perps mark/oracle/funding observation.

    Hyperliquid's ``activeAssetCtx`` message has no exchange timestamp, so the
    local transport receipt time is explicit and must not be presented as venue
    event time.
    """

    symbol: str
    observed_ts_ms: int
    received_ts_ns: int
    mark_price: float
    oracle_price: float
    funding_rate_hourly: float
    open_interest: float
    mid_price: float | None
    timestamp_source: TimestampSource = "local_receive_no_exchange_timestamp"
    source: str = "hyperliquid_ws_activeAssetCtx"

    def __post_init__(self) -> None:
        _nonempty(self.symbol, "symbol")
        _positive_integer(self.observed_ts_ms, "observed_ts_ms")
        _positive_integer(self.received_ts_ns, "received_ts_ns")
        _positive(self.mark_price, "mark_price")
        _positive(self.oracle_price, "oracle_price")
        _finite(self.funding_rate_hourly, "funding_rate_hourly")
        _nonnegative(self.open_interest, "open_interest")
        if self.mid_price is not None:
            _positive(self.mid_price, "mid_price")
        if self.timestamp_source != "local_receive_no_exchange_timestamp":
            raise ValueError("activeAssetCtx timestamp source must remain explicit")

    @property
    def utc_date(self) -> str:
        """Return the local receipt timestamp's UTC calendar date."""
        return _utc_date_ns(self.received_ts_ns)

    @property
    def event_key(self) -> str:
        """Return a stable identity for one locally timestamped observation."""
        identity = asdict(self)
        payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StreamGap:
    """Declared interval where public event completeness is unknown."""

    symbol: str
    channel: str
    detected_ts_ns: int
    reason: str
    previous_exchange_ts_ms: int | None
    next_exchange_ts_ms: int | None

    def __post_init__(self) -> None:
        _nonempty(self.symbol, "symbol")
        _nonempty(self.channel, "channel")
        _positive_integer(self.detected_ts_ns, "detected_ts_ns")
        _nonempty(self.reason, "reason")
        for key, value in (
            ("previous_exchange_ts_ms", self.previous_exchange_ts_ms),
            ("next_exchange_ts_ms", self.next_exchange_ts_ms),
        ):
            if value is not None:
                _positive_integer(value, key)

    @property
    def utc_date(self) -> str:
        """Return the local detection timestamp's UTC calendar date."""
        return _utc_date_ns(self.detected_ts_ns)


def parse_hl_message(
    message: Mapping[str, object],
    *,
    received_ts_ns: int,
) -> tuple[L2SnapshotEvent | PublicTradeEvent | AssetContextEvent, ...]:
    """Normalize one official-shape public WebSocket message."""
    _positive_integer(received_ts_ns, "received_ts_ns")
    channel = _text(message, "channel")
    if channel == "l2Book":
        return (_parse_l2(_mapping(message, "data"), received_ts_ns),)
    if channel == "trades":
        rows = _sequence(message, "data")
        return tuple(_parse_trade(_as_mapping(row), received_ts_ns) for row in rows)
    if channel == "activeAssetCtx":
        return (_parse_asset_context(_mapping(message, "data"), received_ts_ns),)
    if channel in {"subscriptionResponse", "pong"}:
        return ()
    raise ValueError(f"unsupported Hyperliquid channel: {channel}")


def _parse_l2(data: Mapping[str, object], received_ts_ns: int) -> L2SnapshotEvent:
    levels = _sequence(data, "levels")
    if len(levels) != 2:
        raise ValueError("l2Book levels must contain bids and asks")
    bids = tuple(_parse_level(row) for row in _as_sequence(levels[0]))
    asks = tuple(_parse_level(row) for row in _as_sequence(levels[1]))
    return L2SnapshotEvent(
        symbol=_text(data, "coin"),
        exchange_ts_ms=_integer(data, "time"),
        received_ts_ns=received_ts_ns,
        bids=bids,
        asks=asks,
    )


def _parse_level(value: object) -> BookLevel:
    row = _as_mapping(value)
    return BookLevel(
        price=_decimal_text(row, "px", "price"),
        size=_decimal_text(row, "sz", "size"),
        order_count=_integer(row, "n"),
    )


def _parse_trade(data: Mapping[str, object], received_ts_ns: int) -> PublicTradeEvent:
    side = _text(data, "side")
    if side not in {"B", "A"}:
        raise ValueError("trade side must be B|A")
    users = _sequence(data, "users")
    if len(users) != 2 or not all(isinstance(user, str) for user in users):
        raise ValueError("trade users must contain buyer and seller")
    return PublicTradeEvent(
        symbol=_text(data, "coin"),
        aggressor_side=cast(AggressorSide, "buy" if side == "B" else "sell"),
        price=_decimal_text(data, "px", "price"),
        size=_decimal_text(data, "sz", "size"),
        transaction_hash=_text(data, "hash"),
        exchange_ts_ms=_integer(data, "time"),
        received_ts_ns=received_ts_ns,
        trade_id=_integer(data, "tid"),
        buyer=cast(str, users[0]),
        seller=cast(str, users[1]),
    )


def _parse_asset_context(
    data: Mapping[str, object],
    received_ts_ns: int,
) -> AssetContextEvent:
    ctx = _mapping(data, "ctx")
    return AssetContextEvent(
        symbol=_text(data, "coin"),
        observed_ts_ms=received_ts_ns // 1_000_000,
        received_ts_ns=received_ts_ns,
        mark_price=_decimal_text(ctx, "markPx", "mark_price"),
        oracle_price=_decimal_text(ctx, "oraclePx", "oracle_price"),
        funding_rate_hourly=_finite_decimal_text(
            ctx,
            "funding",
            "funding_rate_hourly",
        ),
        open_interest=_nonnegative_decimal_text(
            ctx,
            "openInterest",
            "open_interest",
        ),
        mid_price=_optional_positive_decimal_text(ctx, "midPx", "mid_price"),
    )


def _mapping(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _as_mapping(values.get(key))


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("expected JSON object")
    return value


def _sequence(values: Mapping[str, object], key: str) -> list[object]:
    return _as_sequence(values.get(key))


def _as_sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected JSON array")
    return value


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _decimal_text(values: Mapping[str, object], key: str, label: str) -> float:
    value = values.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a decimal string")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    _positive(parsed, label)
    return parsed


def _finite_decimal_text(
    values: Mapping[str, object],
    key: str,
    label: str,
) -> float:
    value = values.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a decimal string")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    _finite(parsed, label)
    return parsed


def _nonnegative_decimal_text(
    values: Mapping[str, object],
    key: str,
    label: str,
) -> float:
    parsed = _finite_decimal_text(values, key, label)
    _nonnegative(parsed, label)
    return parsed


def _optional_positive_decimal_text(
    values: Mapping[str, object],
    key: str,
    label: str,
) -> float | None:
    if values.get(key) is None:
        return None
    parsed = _finite_decimal_text(values, key, label)
    _positive(parsed, label)
    return parsed


def _positive(value: float, key: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
        raise ValueError(f"{key} must be positive and finite")


def _nonnegative(value: float, key: str) -> None:
    _finite(value, key)
    if value < 0.0:
        raise ValueError(f"{key} must be non-negative")


def _finite(value: float, key: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be finite")


def _positive_integer(value: int, key: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")


def _nonnegative_integer(value: int, key: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")


def _nonempty(value: str, key: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty")


def _utc_date_ms(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1_000.0, tz=UTC).date().isoformat()


def _utc_date_ns(timestamp: int) -> str:
    return (
        datetime.fromtimestamp(timestamp / 1_000_000_000.0, tz=UTC).date().isoformat()
    )
