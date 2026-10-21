"""Symbol-parameterized parsing for official Hyperliquid perpetual responses."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.hyperliquid_protocol import (
    HyperliquidAccountSnapshot,
    HyperliquidBookLevel,
    HyperliquidBookSnapshot,
    HyperliquidFundingPayment,
    HyperliquidMarketMetadata,
    HyperliquidPositionSnapshot,
)
from hypervector.live.hyperliquid_parsing import (
    HyperliquidAdapterError,
    mapping,
    nonnegative_integer,
    nonnegative_number,
    number,
    optional_number,
    positive_integer,
    positive_number,
    sequence,
    text,
)

_PERP_MAX_DECIMALS = 6


def parse_market_for_symbol(value: object, symbol: str) -> HyperliquidMarketMetadata:
    """Parse exactly one requested perpetual market metadata record."""
    universe = sequence(
        mapping(value, "market metadata").get("universe"), "market universe"
    )
    matches = [
        mapping(item, "market")
        for item in universe
        if mapping(item, "market").get("name") == symbol
    ]
    if len(matches) != 1:
        raise HyperliquidAdapterError(
            f"{symbol} metadata must contain exactly one market"
        )
    market = matches[0]
    decimals = nonnegative_integer(market.get("szDecimals"), f"{symbol} szDecimals")
    if decimals > _PERP_MAX_DECIMALS:
        raise HyperliquidAdapterError(f"{symbol} szDecimals exceeds perp precision")
    leverage = positive_integer(market.get("maxLeverage"), f"{symbol} maxLeverage")
    return HyperliquidMarketMetadata(symbol, decimals, leverage)


def parse_mid_for_symbol(value: object, symbol: str) -> float:
    """Parse one requested perpetual midpoint from all-mids output."""
    return positive_number(mapping(value, "all mids").get(symbol), f"{symbol} midpoint")


def parse_book_for_symbol(
    value: object,
    *,
    symbol: str,
    depth_levels: int,
) -> HyperliquidBookSnapshot:
    """Parse one strict two-sided L2 snapshot for a requested market."""
    depth = positive_integer(depth_levels, "depth_levels")
    book = mapping(value, f"{symbol} L2 book")
    if book.get("coin") != symbol:
        raise HyperliquidAdapterError(f"L2 book coin must be {symbol}")
    timestamp = nonnegative_integer(book.get("time"), "L2 book time")
    sides = sequence(book.get("levels"), "L2 book levels")
    if len(sides) != 2:
        raise HyperliquidAdapterError("L2 book must contain bid and ask sides")
    bids = _book_side(sides[0], "bid", depth)
    asks = _book_side(sides[1], "ask", depth)
    _ordered(bids, descending=True, label="bid")
    _ordered(asks, descending=False, label="ask")
    if bids[0].price >= asks[0].price:
        raise HyperliquidAdapterError(f"{symbol} L2 book is crossed or locked")
    mid = (bids[0].price + asks[0].price) / 2.0
    bid_depth = sum(level.size for level in bids)
    ask_depth = sum(level.size for level in asks)
    return HyperliquidBookSnapshot(
        exchange_timestamp_ms=timestamp,
        bids=bids,
        asks=asks,
        mid_price=mid,
        spread_bps=(asks[0].price - bids[0].price) / mid * 10_000.0,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        order_pressure=(bid_depth - ask_depth) / (bid_depth + ask_depth),
    )


def parse_account_for_symbol(value: object, symbol: str) -> HyperliquidAccountSnapshot:
    """Parse clearinghouse totals and only the requested symbol position."""
    state = mapping(value, "clearinghouse state")
    summary = mapping(state.get("marginSummary"), "margin summary")
    positions = _position_records(state)
    matches = [position for position in positions if position.get("coin") == symbol]
    if len(matches) > 1:
        raise HyperliquidAdapterError(f"duplicate {symbol} positions returned")
    position = _position(matches[0], symbol) if matches else _flat_position()
    return HyperliquidAccountSnapshot(
        account_value_usd=number(summary.get("accountValue"), "accountValue"),
        withdrawable_usd=number(state.get("withdrawable"), "withdrawable"),
        total_margin_used_usd=nonnegative_number(
            summary.get("totalMarginUsed"), "totalMarginUsed"
        ),
        total_notional_position_usd=nonnegative_number(
            summary.get("totalNtlPos"), "totalNtlPos"
        ),
        position=position,
        balance_source="perp_clearinghouse_state",
    )


def parse_account_mode_for_symbol(
    *,
    mode: str,
    perp_state: object,
    spot_state: object | None,
    symbol: str,
) -> HyperliquidAccountSnapshot:
    """Parse legacy or unified equity while selecting one symbol position."""
    legacy = parse_account_for_symbol(perp_state, symbol)
    if mode != "unifiedAccount":
        return legacy
    if spot_state is None:
        raise HyperliquidAdapterError("unified account requires spot state")
    positions = _position_records(mapping(perp_state, "clearinghouse state"))
    total, hold = _usdc_balance(spot_state)
    margin = sum(
        nonnegative_number(item.get("marginUsed"), "marginUsed") for item in positions
    )
    notional = sum(
        nonnegative_number(item.get("positionValue"), "positionValue")
        for item in positions
    )
    return HyperliquidAccountSnapshot(
        account_value_usd=total,
        withdrawable_usd=max(0.0, total - hold),
        total_margin_used_usd=margin,
        total_notional_position_usd=notional,
        position=legacy.position,
        balance_source="spot_clearinghouse_state",
    )


def parse_funding_for_symbol(
    value: object, symbol: str
) -> tuple[HyperliquidFundingPayment, ...]:
    """Parse only funding ledger entries for the requested market."""
    payments: list[HyperliquidFundingPayment] = []
    for item in sequence(value, "user funding history"):
        record = mapping(item, "funding record")
        delta = mapping(record.get("delta"), "funding delta")
        if delta.get("coin") != symbol:
            continue
        if delta.get("type") != "funding":
            raise HyperliquidAdapterError(f"{symbol} funding delta type is invalid")
        payments.append(
            HyperliquidFundingPayment(
                timestamp_ms=nonnegative_integer(record.get("time"), "funding time"),
                usdc_delta=number(delta.get("usdc"), "funding usdc"),
                position_size_signed=number(delta.get("szi"), "funding szi"),
                funding_rate=number(delta.get("fundingRate"), "funding rate"),
                transaction_hash=text(record.get("hash"), "funding hash"),
            )
        )
    return tuple(payments)


def _book_side(value: object, label: str, depth: int) -> tuple[HyperliquidBookLevel, ...]:
    rows = sequence(value, f"L2 {label} levels")
    if not rows:
        raise HyperliquidAdapterError(f"L2 {label} side must not be empty")
    return tuple(
        HyperliquidBookLevel(
            price=positive_number(mapping(item, label).get("px"), f"{label} px"),
            size=positive_number(mapping(item, label).get("sz"), f"{label} sz"),
            order_count=nonnegative_integer(
                mapping(item, label).get("n"), f"{label} n"
            ),
        )
        for item in rows[:depth]
    )


def _ordered(
    levels: tuple[HyperliquidBookLevel, ...],
    *,
    descending: bool,
    label: str,
) -> None:
    pairs = zip(levels, levels[1:], strict=False)
    valid = all(
        left.price > right.price if descending else left.price < right.price
        for left, right in pairs
    )
    if not valid:
        raise HyperliquidAdapterError(f"L2 {label} prices are not strictly ordered")


def _position_records(state: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    return tuple(
        mapping(mapping(item, "asset position").get("position"), "position")
        for item in sequence(state.get("assetPositions"), "asset positions")
    )


def _position(value: Mapping[str, object], symbol: str) -> HyperliquidPositionSnapshot:
    size = number(value.get("szi"), f"{symbol} position size")
    leverage = mapping(value.get("leverage"), f"{symbol} leverage")
    leverage_type = text(leverage.get("type"), f"{symbol} leverage type")
    if size != 0.0 and leverage_type != "isolated":
        raise HyperliquidAdapterError(f"nonzero {symbol} position must be isolated")
    return HyperliquidPositionSnapshot(
        size_signed=size,
        entry_price=optional_number(value.get("entryPx"), "entryPx"),
        liquidation_price=optional_number(value.get("liquidationPx"), "liquidationPx"),
        margin_used_usd=nonnegative_number(value.get("marginUsed"), "marginUsed"),
        position_value_usd=nonnegative_number(
            value.get("positionValue"), "positionValue"
        ),
        unrealized_pnl_usd=number(value.get("unrealizedPnl"), "unrealizedPnl"),
        leverage_type=leverage_type,
        leverage=positive_integer(leverage.get("value"), f"{symbol} leverage value"),
    )


def _flat_position() -> HyperliquidPositionSnapshot:
    return HyperliquidPositionSnapshot(0.0, None, None, 0.0, 0.0, 0.0, None, None)


def _usdc_balance(value: object) -> tuple[float, float]:
    balances = sequence(mapping(value, "spot state").get("balances"), "spot balances")
    matches = [
        mapping(item, "spot balance")
        for item in balances
        if mapping(item, "spot balance").get("coin") == "USDC"
    ]
    if len(matches) != 1:
        raise HyperliquidAdapterError("unified spot state requires one USDC balance")
    total = nonnegative_number(matches[0].get("total"), "USDC total")
    hold = nonnegative_number(matches[0].get("hold"), "USDC hold")
    if hold > total:
        raise HyperliquidAdapterError("USDC hold exceeds total")
    return total, hold
