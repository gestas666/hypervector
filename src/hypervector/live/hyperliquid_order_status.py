"""Native order status and cancel receipts without invented execution quantities."""

from collections.abc import Mapping

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
)
from hypervector.live.hyperliquid_parsing import (
    HyperliquidAdapterError,
    HyperliquidOrderUnavailableError,
    _ack_statuses,
    _top_level_error,
    mapping,
    nonnegative_integer,
    nonnegative_number,
    optional_number,
    positive_integer,
    text,
)
from hypervector.live.asset_order_identity import validate_client_order_id


def parse_order_status(
    value: object,
    *,
    expected_oid: int | None = None,
    expected_client_order_id: str | None = None,
) -> HyperliquidOrderStatus:
    """Validate exact identity; size is remaining, not an executed-fill total."""
    if (expected_oid is None) == (expected_client_order_id is None):
        raise HyperliquidAdapterError("order status requires exactly one expected order identity")
    response = mapping(value, "order status response")
    if response.get("status") == "unknownOid":
        raise HyperliquidOrderUnavailableError(
            f"order {expected_oid or expected_client_order_id} status is not yet visible"
        )
    if response.get("status") != "order":
        raise HyperliquidAdapterError("order status response has an unknown status")
    outer = mapping(response.get("order"), "order status")
    order = mapping(outer.get("order"), "order status details")
    oid = positive_integer(order.get("oid"), "order status oid")
    if expected_oid is not None and oid != expected_oid:
        raise HyperliquidAdapterError(
            f"order status oid mismatch: expected {expected_oid}, observed {oid}"
        )
    raw_client_id = order.get("cloid")
    client_id = (
        None
        if raw_client_id is None
        else validate_client_order_id(text(raw_client_id, "order status cloid"))
    )
    if expected_client_order_id is not None and client_id != expected_client_order_id:
        raise HyperliquidAdapterError(
            f"order status client order id mismatch: expected {expected_client_order_id}, observed {client_id}"
        )
    status = text(outer.get("status"), "order status")
    remaining, original = _quantities(order, status)
    return HyperliquidOrderStatus(
        oid=oid,
        symbol=text(order.get("coin"), "order status coin"),
        status=status,
        size=remaining,
        status_timestamp_ms=nonnegative_integer(
            outer.get("statusTimestamp"), "order status timestamp"
        ),
        client_order_id=client_id,
        original_size=original,
    )


def _quantities(order: Mapping[str, object], status: str) -> tuple[float, float | None]:
    remaining = nonnegative_number(order.get("sz"), "order remaining size")
    original = optional_number(order.get("origSz"), "order original size")
    if original is not None and (original <= 0 or remaining > original):
        raise HyperliquidAdapterError(
            "order original size must be positive and at least remaining size"
        )
    if status == "open" and remaining == 0:
        raise HyperliquidAdapterError("open order remaining size must be positive")
    return remaining, original


def parse_cancel_ack(value: object, oid: int) -> HyperliquidOrderAck:
    """Normalize an exact-order cancellation response."""
    response = mapping(value, "cancel response")
    error = _top_level_error(response)
    if error is not None:
        return HyperliquidOrderAck(False, oid, "error", error=error)
    statuses = _ack_statuses(response, "cancel")
    if statuses[0] == "success":
        return HyperliquidOrderAck(True, oid, "canceled")
    first = statuses[0]
    if isinstance(first, Mapping) and "error" in first:
        return HyperliquidOrderAck(False, oid, "error", error=str(first["error"]))
    raise HyperliquidAdapterError("cancel returned unknown acknowledgement")
