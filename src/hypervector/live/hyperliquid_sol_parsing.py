"""Strict response parsing for the SOL Hyperliquid adapter boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    SolAccountSnapshot,
    SolBookLevel,
    SolBookSnapshot,
    SolFill,
    SolFundingPayment,
    SolMarketMetadata,
    SolOpenOrder,
    SolPositionSnapshot,
)
from hypervector.live.sol_order_identity import validate_client_order_id

SOL_SYMBOL = "SOL"
_PRICE_SIGNIFICANT_FIGURES, _PERP_MAX_DECIMAL_BASE = 5, 6


class HyperliquidAdapterError(RuntimeError):
    """A venue response or requested operation violated the canary contract."""


class HyperliquidOrderUnavailableError(HyperliquidAdapterError):
    """An exact order identity is not yet visible from the info endpoint."""


def parse_market(value: object) -> SolMarketMetadata:
    """Parse exactly one SOL perpetual metadata record."""
    metadata = mapping(value, "market metadata")
    universe = sequence(metadata.get("universe"), "market universe")
    matches = [
        mapping(item, "market")
        for item in universe
        if mapping(item, "market").get("name") == SOL_SYMBOL
    ]
    if len(matches) != 1:
        raise HyperliquidAdapterError("SOL metadata must contain exactly one market")
    market = matches[0]
    size_decimals = nonnegative_integer(market.get("szDecimals"), "SOL szDecimals")
    if size_decimals > _PERP_MAX_DECIMAL_BASE:
        raise HyperliquidAdapterError("SOL szDecimals exceeds perp price precision")
    max_leverage = positive_integer(market.get("maxLeverage"), "SOL maxLeverage")
    return SolMarketMetadata(SOL_SYMBOL, size_decimals, max_leverage)


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


def parse_sol_mid(value: object) -> float:
    """Parse the current SOL midpoint from all-mids output."""
    mids = mapping(value, "all mids")
    return positive_number(mids.get(SOL_SYMBOL), "SOL midpoint")


def parse_l2_book(value: object, *, depth_levels: int) -> SolBookSnapshot:
    """Parse one strict SOL L2 snapshot and its displayed depth metrics."""
    depth = positive_integer(depth_levels, "depth_levels")
    book = mapping(value, "SOL L2 book")
    if book.get("coin") != SOL_SYMBOL:
        raise HyperliquidAdapterError("L2 book coin must be SOL")
    timestamp = nonnegative_integer(book.get("time"), "L2 book time")
    sides = sequence(book.get("levels"), "L2 book levels")
    if len(sides) != 2:
        raise HyperliquidAdapterError("L2 book must contain bid and ask sides")
    bids = _parse_book_side(sides[0], "bid", depth)
    asks = _parse_book_side(sides[1], "ask", depth)
    _validate_book_order(bids, descending=True, label="bid")
    _validate_book_order(asks, descending=False, label="ask")
    best_bid = bids[0].price
    best_ask = asks[0].price
    if best_bid >= best_ask:
        raise HyperliquidAdapterError("SOL L2 book is crossed or locked")
    mid = (best_bid + best_ask) / 2.0
    bid_depth = sum(level.size for level in bids)
    ask_depth = sum(level.size for level in asks)
    total_depth = bid_depth + ask_depth
    return SolBookSnapshot(
        exchange_timestamp_ms=timestamp,
        bids=bids,
        asks=asks,
        mid_price=mid,
        spread_bps=(best_ask - best_bid) / mid * 10_000.0,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        order_pressure=(bid_depth - ask_depth) / total_depth,
    )


def _parse_book_side(
    value: object,
    label: str,
    depth: int,
) -> tuple[SolBookLevel, ...]:
    raw = sequence(value, f"L2 {label} levels")
    if not raw:
        raise HyperliquidAdapterError(f"L2 {label} side must not be empty")
    return tuple(_parse_book_level(item, label) for item in raw[:depth])


def _parse_book_level(value: object, label: str) -> SolBookLevel:
    level = mapping(value, f"L2 {label} level")
    return SolBookLevel(
        price=positive_number(level.get("px"), f"{label} px"),
        size=positive_number(level.get("sz"), f"{label} sz"),
        order_count=nonnegative_integer(level.get("n"), f"{label} order count"),
    )


def _validate_book_order(
    levels: tuple[SolBookLevel, ...],
    *,
    descending: bool,
    label: str,
) -> None:
    prices = [level.price for level in levels]
    pairs = zip(prices, prices[1:], strict=False)
    valid = all(left > right if descending else left < right for left, right in pairs)
    if not valid:
        raise HyperliquidAdapterError(f"L2 {label} prices are not strictly ordered")


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


def parse_account(value: object) -> SolAccountSnapshot:
    """Parse clearinghouse values and the unique SOL position."""
    state = mapping(value, "clearinghouse state")
    summary = mapping(state.get("marginSummary"), "margin summary")
    positions = sequence(state.get("assetPositions"), "asset positions")
    sol_positions = _sol_position_records(positions)
    if len(sol_positions) > 1:
        raise HyperliquidAdapterError("clearinghouse returned duplicate SOL positions")
    position = _parse_position(sol_positions[0]) if sol_positions else _flat_position()
    return SolAccountSnapshot(
        account_value_usd=number(summary.get("accountValue"), "accountValue"),
        withdrawable_usd=number(state.get("withdrawable"), "withdrawable"),
        total_margin_used_usd=nonnegative_number(
            summary.get("totalMarginUsed"),
            "totalMarginUsed",
        ),
        total_notional_position_usd=nonnegative_number(
            summary.get("totalNtlPos"),
            "totalNtlPos",
        ),
        position=position,
        balance_source="perp_clearinghouse_state",
    )


def _sol_position_records(values: Sequence[object]) -> list[Mapping[str, object]]:
    matches: list[Mapping[str, object]] = []
    for item in values:
        wrapper = mapping(item, "asset position")
        position = mapping(wrapper.get("position"), "position")
        if position.get("coin") == SOL_SYMBOL:
            matches.append(position)
    return matches


def _parse_position(value: Mapping[str, object]) -> SolPositionSnapshot:
    size = number(value.get("szi"), "SOL position size")
    leverage = mapping(value.get("leverage"), "SOL leverage")
    leverage_type = text(leverage.get("type"), "SOL leverage type")
    if size != 0.0 and leverage_type != "isolated":
        raise HyperliquidAdapterError("nonzero SOL position must use isolated leverage")
    return SolPositionSnapshot(
        size_signed=size,
        entry_price=optional_number(value.get("entryPx"), "entryPx"),
        liquidation_price=optional_number(value.get("liquidationPx"), "liquidationPx"),
        margin_used_usd=nonnegative_number(value.get("marginUsed"), "marginUsed"),
        position_value_usd=nonnegative_number(
            value.get("positionValue"), "positionValue"
        ),
        unrealized_pnl_usd=number(value.get("unrealizedPnl"), "unrealizedPnl"),
        leverage_type=leverage_type,
        leverage=positive_integer(leverage.get("value"), "SOL leverage value"),
    )


def _flat_position() -> SolPositionSnapshot:
    return SolPositionSnapshot(
        size_signed=0.0,
        entry_price=None,
        liquidation_price=None,
        margin_used_usd=0.0,
        position_value_usd=0.0,
        unrealized_pnl_usd=0.0,
        leverage_type=None,
        leverage=None,
    )


def parse_open_order(value: object) -> SolOpenOrder:
    """Parse one frontend-open-order record."""
    order = mapping(value, "open order")
    return SolOpenOrder(
        oid=positive_integer(order.get("oid"), "open order oid"),
        size=positive_number(order.get("sz"), "open order size"),
        original_size=positive_number(order.get("origSz"), "open order original size"),
        side=text(order.get("side"), "open order side"),
        reduce_only=boolean(order.get("reduceOnly"), "open order reduceOnly"),
        is_trigger=boolean(order.get("isTrigger"), "open order isTrigger"),
        trigger_price=optional_number(order.get("triggerPx"), "triggerPx"),
        order_type=text(order.get("orderType"), "open order type"),
        timestamp_ms=nonnegative_integer(
            order.get("timestamp"), "open order timestamp"
        ),
        limit_price=optional_number(order.get("limitPx"), "limitPx"),
    )


def parse_fill(value: object) -> SolFill:
    """Parse one user-fill record including signed fee and PnL."""
    fill = mapping(value, "fill")
    return SolFill(
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


def parse_funding_payments(value: object) -> tuple[SolFundingPayment, ...]:
    """Parse SOL entries from the official user-funding response schema."""
    payments: list[SolFundingPayment] = []
    for item in sequence(value, "user funding history"):
        record = mapping(item, "funding record")
        delta = mapping(record.get("delta"), "funding delta")
        if delta.get("coin") != SOL_SYMBOL:
            continue
        if delta.get("type") != "funding":
            raise HyperliquidAdapterError("SOL funding delta has an unexpected type")
        payments.append(
            SolFundingPayment(
                timestamp_ms=nonnegative_integer(record.get("time"), "funding time"),
                usdc_delta=number(delta.get("usdc"), "funding usdc"),
                position_size_signed=number(delta.get("szi"), "funding szi"),
                funding_rate=number(delta.get("fundingRate"), "funding rate"),
                transaction_hash=text(record.get("hash"), "funding hash"),
            )
        )
    return tuple(payments)


def parse_order_status(
    value: object,
    *,
    expected_oid: int | None = None,
    expected_client_order_id: str | None = None,
) -> HyperliquidOrderStatus:
    """Parse and identity-check one order-status response."""
    if (expected_oid is None) == (expected_client_order_id is None):
        raise HyperliquidAdapterError(
            "order status requires exactly one expected order identity"
        )
    response = mapping(value, "order status response")
    if response.get("status") == "unknownOid":
        identity = expected_oid or expected_client_order_id
        raise HyperliquidOrderUnavailableError(
            f"order {identity} status is not yet visible"
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
            "order status client order id mismatch: "
            f"expected {expected_client_order_id}, observed {client_id}"
        )
    return HyperliquidOrderStatus(
        oid=oid,
        symbol=text(order.get("coin"), "order status coin"),
        status=text(outer.get("status"), "order status"),
        size=positive_number(order.get("sz"), "order status size"),
        status_timestamp_ms=nonnegative_integer(
            outer.get("statusTimestamp"),
            "order status timestamp",
        ),
        client_order_id=client_id,
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
            HyperliquidOrderAck(False, None, "error", error=error)
            for _ in range(expected_count)
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
    raise HyperliquidAdapterError(
        f"{operation} status {index} returned unknown acknowledgement"
    )


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
    raise HyperliquidAdapterError(f"unsupported SOL entry side: {side!r}")


def validate_address(value: str) -> str:
    """Validate an account address without returning or logging credentials."""
    address = value.strip()
    if len(address) != 42 or not address.startswith("0x"):
        raise HyperliquidAdapterError(
            "account_address must be a 42-character 0x address"
        )
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
    (SolBookLevel,)
    (SolBookSnapshot,)
