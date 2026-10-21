"""Strict response-parsing primitives shared by the Hyperliquid adapters."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    HyperliquidBookLevel,
    HyperliquidBookSnapshot,
    HyperliquidFill,
    HyperliquidOpenOrder,
)

_PRICE_SIGNIFICANT_FIGURES, _PERP_MAX_DECIMAL_BASE = 5, 6


class HyperliquidAdapterError(RuntimeError):
    """A venue response or requested operation violated the adapter contract."""


class HyperliquidOrderUnavailableError(HyperliquidAdapterError):
    """An exact order identity is not yet visible from the info endpoint."""


def parse_fees(value: object) -> HyperliquidFeeSchedule:
    """Parse account base rates and the active referral discount."""
    fees = mapping(value, "user fees")
    return HyperliquidFeeSchedule(
        maker_rate=number(fees.get("userAddRate"), "userAddRate"),
        taker_rate=nonnegative_number(fees.get("userCrossRate"), "userCrossRate"),
        active_referral_discount=nonnegative_number(
            fees.get("activeReferralDiscount"),
            "activeReferralDiscount",
        ),
    )


def price_tick(mark_price: float, size_decimals: int) -> float:
    """Derive the SDK-compatible price increment at the current magnitude."""
    digits_left = max(1, math.floor(math.log10(mark_price)) + 1)
    significant_decimals = max(0, _PRICE_SIGNIFICANT_FIGURES - digits_left)
    maximum_decimals = _PERP_MAX_DECIMAL_BASE - size_decimals
    return 10.0 ** (-min(significant_decimals, maximum_decimals))


def normalize_perp_price(value: float, size_decimals: int) -> float:
    """Apply the official SDK's five-significant-figure perp wire rounding."""
    price = positive_number(value, "perp price")
    decimals = nonnegative_integer(size_decimals, "size_decimals")
    if decimals > _PERP_MAX_DECIMAL_BASE:
        raise HyperliquidAdapterError("size_decimals exceeds perp price precision")
    significant = float(f"{price:.{_PRICE_SIGNIFICANT_FIGURES}g}")
    return round(significant, _PERP_MAX_DECIMAL_BASE - decimals)


def parse_open_order(value: object) -> HyperliquidOpenOrder:
    """Parse one frontend-open-order record."""
    order = mapping(value, "open order")
    return HyperliquidOpenOrder(
        oid=positive_integer(order.get("oid"), "open order oid"),
        size=positive_number(order.get("sz"), "open order size"),
        original_size=positive_number(order.get("origSz"), "open order original size"),
        side=text(order.get("side"), "open order side"),
        reduce_only=boolean(order.get("reduceOnly"), "open order reduceOnly"),
        is_trigger=boolean(order.get("isTrigger"), "open order isTrigger"),
        trigger_price=optional_number(order.get("triggerPx"), "triggerPx"),
        order_type=text(order.get("orderType"), "open order type"),
        timestamp_ms=nonnegative_integer(order.get("timestamp"), "open order timestamp"),
        limit_price=optional_number(order.get("limitPx"), "limitPx"),
    )


def parse_fill(value: object) -> HyperliquidFill:
    """Parse one user-fill record including signed fee and PnL."""
    fill = mapping(value, "fill")
    return HyperliquidFill(
        oid=positive_integer(fill.get("oid"), "fill oid"),
        price=positive_number(fill.get("px"), "fill price"),
        size=positive_number(fill.get("sz"), "fill size"),
        side=text(fill.get("side"), "fill side"),
        timestamp_ms=nonnegative_integer(fill.get("time"), "fill time"),
        fee_usd=number(fill.get("fee", 0.0), "fill fee"),
        fee_token=text(fill.get("feeToken", "USDC"), "fill fee token"),
        closed_pnl_usd=number(fill.get("closedPnl", 0.0), "fill closedPnl"),
        crossed=boolean(fill.get("crossed"), "fill crossed"),
        direction=text(fill.get("dir"), "fill direction"),
        transaction_hash=text(fill.get("hash"), "fill hash"),
        trade_id=positive_integer(fill.get("tid"), "fill tid"),
    )


def parse_order_status(
    value: object,
    *,
    expected_oid: int | None = None,
    expected_client_order_id: str | None = None,
) -> HyperliquidOrderStatus:
    """Parse remaining/original quantities and verify exact order identity."""
    from hypervector.live.hyperliquid_order_status import (
        parse_order_status as parse_status,
    )

    return parse_status(
        value,
        expected_oid=expected_oid,
        expected_client_order_id=expected_client_order_id,
    )


def parse_order_ack(value: object, *, operation: str) -> HyperliquidOrderAck:
    """Normalize a filled, resting, rejected, or malformed order response."""
    return parse_order_acks(value, operation=operation, expected_count=1)[0]


def parse_order_acks(
    value: object,
    *,
    operation: str,
    expected_count: int,
) -> tuple[HyperliquidOrderAck, ...]:
    """Normalize every ordered status from one batched order action."""
    if isinstance(expected_count, bool) or expected_count <= 0:
        raise ValueError("expected_count must be a positive integer")
    response = mapping(value, f"{operation} response")
    error = _top_level_error(response)
    if error is not None:
        return tuple(
            HyperliquidOrderAck(False, None, "error", error=error) for _ in range(expected_count)
        )
    statuses = _ack_statuses(response, operation)
    if len(statuses) != expected_count:
        raise HyperliquidAdapterError(
            f"{operation} returned {len(statuses)} statuses; expected {expected_count}"
        )
    return tuple(
        _parse_order_status(status, operation=operation, index=index)
        for index, status in enumerate(statuses)
    )


def _parse_order_status(
    value: object,
    *,
    operation: str,
    index: int,
) -> HyperliquidOrderAck:
    first = mapping(value, f"{operation} status {index}")
    if "error" in first:
        return HyperliquidOrderAck(False, None, "error", error=str(first["error"]))
    for status in ("filled", "resting"):
        if status in first:
            details = mapping(first[status], f"{operation} {status}")
            return HyperliquidOrderAck(
                True,
                positive_integer(details.get("oid"), f"{operation} oid"),
                status,
                optional_number(details.get("totalSz"), "filled size"),
                optional_number(details.get("avgPx"), "average price"),
            )
    raise HyperliquidAdapterError(f"{operation} status {index} returned unknown acknowledgement")


def parse_cancel_ack(value: object, oid: int) -> HyperliquidOrderAck:
    """Normalize one exact-order cancellation response."""
    from hypervector.live.hyperliquid_order_status import (
        parse_cancel_ack as parse_cancel,
    )

    return parse_cancel(value, oid)


def _ack_statuses(response: Mapping[str, object], operation: str) -> Sequence[object]:
    envelope = mapping(response.get("response"), f"{operation} response envelope")
    data = mapping(envelope.get("data"), f"{operation} response data")
    statuses = sequence(data.get("statuses"), f"{operation} statuses")
    if not statuses:
        raise HyperliquidAdapterError(f"{operation} response had no statuses")
    return statuses


def _top_level_error(response: Mapping[str, object]) -> str | None:
    status = response.get("status")
    if status in {"err", "error"}:
        return str(response.get("response") or response.get("error") or response)
    return str(response["error"]) if "error" in response else None


def require_ok(value: object, operation: str) -> None:
    """Require a simple successful exchange acknowledgement."""
    response = mapping(value, f"{operation} response")
    error = _top_level_error(response)
    if response.get("status") != "ok" or error is not None:
        raise HyperliquidAdapterError(f"{operation} rejected: {error or response}")


def entry_is_buy(side: str) -> bool:
    """Normalize a strategy entry direction into the SDK buy flag."""
    normalized = side.strip().lower()
    if normalized in {"long", "buy", "b"}:
        return True
    if normalized in {"short", "sell", "s"}:
        return False
    raise HyperliquidAdapterError(f"unsupported entry side: {side!r}")


def validate_address(value: str) -> str:
    """Validate an account address without returning or logging credentials."""
    address = value.strip()
    if len(address) != 42 or not address.startswith("0x"):
        raise HyperliquidAdapterError("account_address must be a 42-character 0x address")
    return address


def mapping(value: object, label: str) -> Mapping[str, object]:
    """Require a string-keyed mapping at an SDK boundary."""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise HyperliquidAdapterError(f"{label} must be an object")
    return value


def sequence(value: object, label: str) -> Sequence[object]:
    """Require a non-text sequence at an SDK boundary."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise HyperliquidAdapterError(f"{label} must be an array")
    return value


def text(value: object, label: str) -> str:
    """Require non-empty text."""
    if not isinstance(value, str) or not value.strip():
        raise HyperliquidAdapterError(f"{label} must be non-empty text")
    return value.strip()


def number(value: object, label: str) -> float:
    """Parse one finite SDK numeric value."""
    if isinstance(value, bool):
        raise HyperliquidAdapterError(f"{label} must be numeric")
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise HyperliquidAdapterError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise HyperliquidAdapterError(f"{label} must be finite")
    return parsed


def positive_number(value: object, label: str) -> float:
    """Parse one positive finite number."""
    parsed = number(value, label)
    if parsed <= 0.0:
        raise HyperliquidAdapterError(f"{label} must be positive")
    return parsed


def nonnegative_number(value: object, label: str) -> float:
    """Parse one nonnegative finite number."""
    parsed = number(value, label)
    if parsed < 0.0:
        raise HyperliquidAdapterError(f"{label} must be nonnegative")
    return parsed


def optional_number(value: object, label: str) -> float | None:
    """Parse a nullable finite number."""
    if value is None or value == "":
        return None
    return number(value, label)


def positive_finite(value: float, label: str) -> float:
    """Validate one positive caller-provided number."""
    return positive_number(value, label)


def nonnegative_finite(value: float, label: str) -> float:
    """Validate one nonnegative caller-provided number."""
    return nonnegative_number(value, label)


def nonzero_finite(value: float, label: str) -> float:
    """Validate one nonzero caller-provided number."""
    parsed = number(value, label)
    if parsed == 0.0:
        raise HyperliquidAdapterError(f"{label} must be nonzero")
    return parsed


def positive_integer(value: object, label: str) -> int:
    """Require a positive integer without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HyperliquidAdapterError(f"{label} must be a positive integer")
    return value


def nonnegative_integer(value: object, label: str) -> int:
    """Require a nonnegative integer without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HyperliquidAdapterError(f"{label} must be a nonnegative integer")
    return value


def boolean(value: object, label: str) -> bool:
    """Require an SDK boolean value."""
    if not isinstance(value, bool):
        raise HyperliquidAdapterError(f"{label} must be boolean")
    return value
    (HyperliquidBookLevel,)
    (HyperliquidBookSnapshot,)
