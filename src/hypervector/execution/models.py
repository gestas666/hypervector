"""Typed, JSON-serializable commands and venue execution events."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal, Mapping, cast

OrderSide = Literal["buy", "sell"]
OrderType = Literal["limit", "market"]
OrderRole = Literal["entry", "target", "exit"]
EventType = Literal[
    "submitted",
    "accepted",
    "rejected",
    "partially_filled",
    "filled",
    "cancel_pending",
    "canceled",
    "expired",
]
LiquiditySide = Literal["maker", "taker"]
MarginMode = Literal["isolated", "cross"]


@dataclass(frozen=True)
class OrderCommand:
    """One backend-authoritative order request for an execution port."""

    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    order_role: OrderRole
    limit_price: float | None
    post_only: bool
    reduce_only: bool
    submitted_at: str

    def __post_init__(self) -> None:
        _nonempty(self.client_order_id, "client_order_id")
        _nonempty(self.symbol, "symbol")
        _member(self.side, "side", ("buy", "sell"))
        _positive(self.quantity, "quantity")
        _member(self.order_type, "order_type", ("limit", "market"))
        _member(self.order_role, "order_role", ("entry", "target", "exit"))
        if self.order_type == "limit":
            _positive(self.limit_price, "limit_price")
        elif self.limit_price is not None:
            raise ValueError("market commands cannot carry limit_price")
        if self.post_only and self.order_type != "limit":
            raise ValueError("post_only commands must use order_type='limit'")
        if self.order_role in {"target", "exit"} and not self.reduce_only:
            raise ValueError("target and exit commands must set reduce_only=True")
        if self.order_role == "entry" and self.reduce_only:
            raise ValueError("entry commands cannot set reduce_only=True")
        _utc_timestamp(self.submitted_at, "submitted_at")

    def to_json(self) -> str:
        """Serialize this validated command to stable JSON."""
        return _to_json(asdict(self))

    @classmethod
    def from_json(cls, payload: str) -> OrderCommand:
        """Parse and validate one command from JSON."""
        raw = _json_object(payload)
        return cls(
            client_order_id=_text(raw, "client_order_id"),
            symbol=_text(raw, "symbol"),
            side=cast(OrderSide, _choice(raw, "side", ("buy", "sell"))),
            quantity=_number(raw, "quantity"),
            order_type=cast(
                OrderType,
                _choice(raw, "order_type", ("limit", "market")),
            ),
            order_role=cast(
                OrderRole,
                _choice(raw, "order_role", ("entry", "target", "exit")),
            ),
            limit_price=_optional_number(raw, "limit_price"),
            post_only=_boolean(raw, "post_only"),
            reduce_only=_boolean(raw, "reduce_only"),
            submitted_at=_text(raw, "submitted_at"),
        )


@dataclass(frozen=True)
class VenueOrderEvent:
    """One normalized venue order-state or fill transition."""

    client_order_id: str
    venue_order_id: str | None
    event_type: EventType
    event_at: str
    last_quantity: float
    cumulative_quantity: float
    fill_price: float | None
    fee_usd: float
    liquidity_side: LiquiditySide | None
    reason: str | None

    def __post_init__(self) -> None:
        _nonempty(self.client_order_id, "client_order_id")
        if self.venue_order_id is not None:
            _nonempty(self.venue_order_id, "venue_order_id")
        _member(self.event_type, "event_type", _EVENT_TYPES)
        _utc_timestamp(self.event_at, "event_at")
        _nonnegative(self.last_quantity, "last_quantity")
        _nonnegative(self.cumulative_quantity, "cumulative_quantity")
        if self.last_quantity > self.cumulative_quantity:
            raise ValueError("last_quantity cannot exceed cumulative_quantity")
        if self.fill_price is not None:
            _positive(self.fill_price, "fill_price")
        _nonnegative(self.fee_usd, "fee_usd")
        if self.liquidity_side is not None:
            _member(self.liquidity_side, "liquidity_side", ("maker", "taker"))
        if self.event_type in {"partially_filled", "filled"}:
            if self.fill_price is None or self.last_quantity <= 0.0:
                raise ValueError("fill events require positive quantity and price")
            if self.liquidity_side is None:
                raise ValueError("fill events require liquidity_side")
        elif (
            self.last_quantity != 0.0
            or self.fill_price is not None
            or self.fee_usd != 0.0
            or self.liquidity_side is not None
        ):
            raise ValueError("non-fill events cannot carry fill-specific fields")

    def to_json(self) -> str:
        """Serialize this validated event to stable JSON."""
        return _to_json(asdict(self))

    @classmethod
    def from_json(cls, payload: str) -> VenueOrderEvent:
        """Parse and validate one venue event from JSON."""
        raw = _json_object(payload)
        venue_order_id = _optional_text(raw, "venue_order_id")
        liquidity = _optional_choice(raw, "liquidity_side", ("maker", "taker"))
        return cls(
            client_order_id=_text(raw, "client_order_id"),
            venue_order_id=venue_order_id,
            event_type=cast(EventType, _choice(raw, "event_type", _EVENT_TYPES)),
            event_at=_text(raw, "event_at"),
            last_quantity=_number(raw, "last_quantity"),
            cumulative_quantity=_number(raw, "cumulative_quantity"),
            fill_price=_optional_number(raw, "fill_price"),
            fee_usd=_number(raw, "fee_usd"),
            liquidity_side=cast(LiquiditySide | None, liquidity),
            reason=_optional_text(raw, "reason"),
        )


@dataclass(frozen=True)
class AccountSnapshot:
    """Normalized venue account state needed by execution preflight."""

    observed_at: str
    equity_usd: float
    available_balance_usd: float
    position_quantity: float
    position_average_price: float | None
    margin_mode: MarginMode
    leverage: float
    maker_fee_rate: float
    taker_fee_rate: float

    def __post_init__(self) -> None:
        _utc_timestamp(self.observed_at, "observed_at")
        _nonnegative(self.equity_usd, "equity_usd")
        _nonnegative(self.available_balance_usd, "available_balance_usd")
        _finite(self.position_quantity, "position_quantity")
        if self.position_average_price is not None:
            _positive(self.position_average_price, "position_average_price")
        if self.position_quantity != 0.0 and self.position_average_price is None:
            raise ValueError("open positions require position_average_price")
        _member(self.margin_mode, "margin_mode", ("isolated", "cross"))
        _positive(self.leverage, "leverage")
        _nonnegative(self.maker_fee_rate, "maker_fee_rate")
        _nonnegative(self.taker_fee_rate, "taker_fee_rate")

    def to_json(self) -> str:
        """Serialize this validated account state to stable JSON."""
        return _to_json(asdict(self))

    @classmethod
    def from_json(cls, payload: str) -> AccountSnapshot:
        """Parse and validate one account snapshot from JSON."""
        raw = _json_object(payload)
        return cls(
            observed_at=_text(raw, "observed_at"),
            equity_usd=_number(raw, "equity_usd"),
            available_balance_usd=_number(raw, "available_balance_usd"),
            position_quantity=_number(raw, "position_quantity"),
            position_average_price=_optional_number(raw, "position_average_price"),
            margin_mode=cast(
                MarginMode,
                _choice(raw, "margin_mode", ("isolated", "cross")),
            ),
            leverage=_number(raw, "leverage"),
            maker_fee_rate=_number(raw, "maker_fee_rate"),
            taker_fee_rate=_number(raw, "taker_fee_rate"),
        )


_EVENT_TYPES: tuple[str, ...] = (
    "submitted",
    "accepted",
    "rejected",
    "partially_filled",
    "filled",
    "cancel_pending",
    "canceled",
    "expired",
)


def _to_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_object(payload: str) -> dict[str, object]:
    try:
        value: object = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("execution payload must be valid JSON") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("execution payload must be a JSON object")
    return value


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_text(values: Mapping[str, object], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _optional_number(values: Mapping[str, object], key: str) -> float | None:
    value = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number or null")
    return float(value)


def _boolean(values: Mapping[str, object], key: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _choice(values: Mapping[str, object], key: str, allowed: tuple[str, ...]) -> str:
    value = _text(values, key)
    _member(value, key, allowed)
    return value


def _optional_choice(
    values: Mapping[str, object],
    key: str,
    allowed: tuple[str, ...],
) -> str | None:
    value = _optional_text(values, key)
    if value is not None:
        _member(value, key, allowed)
    return value


def _nonempty(value: str, key: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty")


def _member(value: str, key: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{key} must be one of {allowed!r}")


def _finite(value: float | None, key: str) -> None:
    if value is None or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be finite")


def _positive(value: float | None, key: str) -> None:
    _finite(value, key)
    if value is None or value <= 0.0:
        raise ValueError(f"{key} must be positive")


def _nonnegative(value: float, key: str) -> None:
    _finite(value, key)
    if value < 0.0:
        raise ValueError(f"{key} must be non-negative")


def _utc_timestamp(value: str, key: str) -> None:
    _nonempty(value, key)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{key} must include an explicit UTC offset")
