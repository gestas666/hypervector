"""Fresh, gap-aware WebSocket venue state for the Apex MM canary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import time
from typing import Protocol, cast

from hypervector.data.hl_ws_feed import FeedDisconnect, FeedItem, ReceivedMessage
from hypervector.live.hyperliquid_perp_parsing import (
    parse_account_mode_for_symbol,
    parse_book_for_symbol,
)
from hypervector.live.hyperliquid_protocol import (
    SolBookSnapshot,
    SolFill,
    SolOpenOrder,
    SolReconciliationSnapshot,
)
from hypervector.live.hyperliquid_sol_parsing import (
    boolean,
    mapping,
    nonnegative_integer,
    parse_fill,
    parse_open_order,
    positive_integer,
    positive_number,
    sequence,
    text,
    validate_address,
)

_MAX_CACHED_FILLS = 500
_TERMINAL_ORDER_STATUSES = frozenset(
    {
        "filled",
        "canceled",
        "triggered",
        "rejected",
        "marginCanceled",
        "vaultWithdrawalCanceled",
        "openInterestCapCanceled",
        "selfTradeCanceled",
        "reduceOnlyCanceled",
        "siblingFilledCanceled",
        "delistedCanceled",
        "liquidatedCanceled",
        "scheduledCancel",
        "tickRejected",
        "minTradeNtlRejected",
        "perpMarginRejected",
        "reduceOnlyRejected",
        "badAloPxRejected",
        "iocCancelRejected",
        "badTriggerPxRejected",
        "marketOrderNoLiquidityRejected",
        "positionIncreaseAtOpenInterestCapRejected",
        "positionFlipAtOpenInterestCapRejected",
        "tooAggressiveAtOpenInterestCapRejected",
        "openInterestIncreaseRejected",
        "insufficientSpotBalanceRejected",
        "oracleRejected",
        "perpMaxPositionRejected",
    }
)


class ApexMMVenueStreamError(RuntimeError):
    """Required live venue state is unavailable or stale."""


class ApexMMFeedProtocol(Protocol):
    """Receiver operations required by the venue-state cache."""

    def start(self) -> None: ...

    def wait_for_item(self, *, timeout_seconds: float) -> bool: ...

    def drain(self) -> tuple[FeedItem, ...]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ApexMMVenueStreamSnapshot:
    """One coherent local projection of streamed venue truth."""

    book: SolBookSnapshot
    venue: SolReconciliationSnapshot


def apex_mm_subscription_payloads(
    *,
    symbol: str,
    account_address: str,
) -> tuple[str, ...]:
    """Build the exact public/private subscriptions needed by Apex MM."""
    coin = symbol.strip()
    if not coin:
        raise ValueError("symbol must be non-empty")
    user = validate_address(account_address)
    subscriptions = (
        {"type": "l2Book", "coin": coin},
        {"type": "clearinghouseState", "user": user},
        {"type": "spotState", "user": user},
        {"type": "openOrders", "user": user},
        {"type": "orderUpdates", "user": user},
        {"type": "userFills", "user": user},
    )
    return tuple(_subscription_payload(item) for item in subscriptions)


class ApexMMVenueStream:
    """Normalize streamed book, account, order, and fill state fail-closed."""

    def __init__(
        self,
        *,
        feed: ApexMMFeedProtocol,
        symbol: str,
        account_mode: str,
        depth_levels: int,
        clock_ns: Callable[[], int] = time.time_ns,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if not symbol.strip():
            raise ValueError("symbol must be non-empty")
        if depth_levels <= 0:
            raise ValueError("depth_levels must be positive")
        self._feed = feed
        self._symbol = symbol
        self._account_mode = account_mode
        self._depth_levels = depth_levels
        self._clock_ns = clock_ns
        self._monotonic_fn = monotonic_fn
        self._book: SolBookSnapshot | None = None
        self._book_received_ns: int | None = None
        self._perp_state: object | None = None
        self._spot_state: object | None = None
        self._orders: tuple[SolOpenOrder, ...] | None = None
        self._fills: tuple[SolFill, ...] | None = None
        self._disconnect_reason: str | None = None
        self._started = False

    def start(self, *, timeout_seconds: float) -> None:
        """Start the receiver and require a complete initial venue snapshot."""
        if self._started:
            raise ApexMMVenueStreamError("venue stream already started")
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        self._started = True
        self._feed.start()
        deadline = self._monotonic_fn() + timeout_seconds
        try:
            while not self._ready:
                remaining = deadline - self._monotonic_fn()
                if remaining <= 0.0 or not self._feed.wait_for_item(
                    timeout_seconds=remaining
                ):
                    raise ApexMMVenueStreamError(
                        "venue stream initial snapshot timed out"
                    )
                self._refresh()
        except Exception:
            self._feed.close()
            self._started = False
            raise

    def snapshot(self, *, maximum_age_ms: int) -> ApexMMVenueStreamSnapshot:
        """Return coherent state only while the live book remains fresh."""
        if maximum_age_ms < 0:
            raise ValueError("maximum_age_ms must be non-negative")
        snapshot = self.state_snapshot()
        age_ms = self._book_age_ms()
        if age_ms > maximum_age_ms:
            raise ApexMMVenueStreamError(f"venue stream book is stale: {age_ms:.0f}ms")
        return snapshot

    def state_snapshot(self) -> ApexMMVenueStreamSnapshot:
        """Return account/order state independent of quote-book freshness."""
        if not self._started:
            raise ApexMMVenueStreamError("venue stream is not started")
        self._refresh()
        if self._disconnect_reason is not None:
            raise ApexMMVenueStreamError(
                f"venue stream disconnected: {self._disconnect_reason}"
            )
        if not self._ready:
            raise ApexMMVenueStreamError("venue stream snapshot is incomplete")
        account = parse_account_mode_for_symbol(
            mode=self._account_mode,
            perp_state=self._perp_state,
            spot_state=self._spot_state,
            symbol=self._symbol,
        )
        return ApexMMVenueStreamSnapshot(
            book=cast(SolBookSnapshot, self._book),
            venue=SolReconciliationSnapshot(
                account=account,
                open_orders=cast(tuple[SolOpenOrder, ...], self._orders),
                fills=cast(tuple[SolFill, ...], self._fills),
            ),
        )

    def wait_for_fresh_book(
        self,
        *,
        maximum_age_ms: int,
        timeout_seconds: float,
    ) -> SolBookSnapshot:
        """Wait briefly for a quote-safe L2 snapshot after slow REST work."""
        if maximum_age_ms < 0:
            raise ValueError("maximum_age_ms must be non-negative")
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        deadline = self._monotonic_fn() + timeout_seconds
        while True:
            snapshot = self.state_snapshot()
            if self._book_age_ms() <= maximum_age_ms:
                return snapshot.book
            remaining = deadline - self._monotonic_fn()
            if remaining <= 0.0 or not self._feed.wait_for_item(
                timeout_seconds=remaining
            ):
                raise ApexMMVenueStreamError("fresh venue book timed out")

    def wait_for_open_orders(
        self,
        *,
        expected_oids: frozenset[int],
        timeout_seconds: float,
        maximum_age_ms: int,
    ) -> ApexMMVenueStreamSnapshot:
        """Wait for streamed open-order identity to confirm one mutation set."""
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        deadline = self._monotonic_fn() + timeout_seconds
        while True:
            snapshot = self.state_snapshot()
            observed = frozenset(order.oid for order in snapshot.venue.open_orders)
            if observed == expected_oids:
                return snapshot
            remaining = deadline - self._monotonic_fn()
            if remaining <= 0.0 or not self._feed.wait_for_item(
                timeout_seconds=remaining
            ):
                raise ApexMMVenueStreamError(
                    "venue stream order confirmation timed out"
                )

    def wait_for_fill(
        self,
        *,
        oid: int,
        timeout_seconds: float,
        markout_horizon_ms: int = 0,
    ) -> ApexMMVenueStreamSnapshot:
        """Wait for an exact private fill and a book at its markout horizon."""
        expected = positive_integer(oid, "stream fill oid")
        horizon = nonnegative_integer(markout_horizon_ms, "markout horizon")
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        deadline = self._monotonic_fn() + timeout_seconds
        fill_timestamp_ms: int | None = None
        while True:
            snapshot = self.state_snapshot()
            matching = next(
                (fill for fill in snapshot.venue.fills if fill.oid == expected),
                None,
            )
            if matching is not None and fill_timestamp_ms is None:
                fill_timestamp_ms = matching.timestamp_ms
                deadline = self._monotonic_fn() + timeout_seconds
            if (
                fill_timestamp_ms is not None
                and snapshot.book.exchange_timestamp_ms >= fill_timestamp_ms + horizon
            ):
                return snapshot
            remaining = deadline - self._monotonic_fn()
            if remaining <= 0.0 or not self._feed.wait_for_item(
                timeout_seconds=remaining
            ):
                raise ApexMMVenueStreamError(
                    f"venue stream fill/markout confirmation timed out for oid {expected}"
                )

    def _book_age_ms(self) -> float:
        received_ns = cast(int, self._book_received_ns)
        return max(0.0, (self._clock_ns() - received_ns) / 1_000_000.0)

    def close(self) -> None:
        """Close the receiver; repeated calls are harmless."""
        if self._started:
            self._feed.close()
            self._started = False

    @property
    def _ready(self) -> bool:
        spot_ready = (
            self._account_mode != "unifiedAccount" or self._spot_state is not None
        )
        return (
            self._book is not None
            and self._book_received_ns is not None
            and self._perp_state is not None
            and spot_ready
            and self._orders is not None
            and self._fills is not None
        )

    def _refresh(self) -> None:
        for item in self._feed.drain():
            if isinstance(item, FeedDisconnect):
                self._invalidate(item.reason)
            else:
                self._ingest(item)
        if self._ready:
            self._disconnect_reason = None

    def _ingest(self, item: ReceivedMessage) -> None:
        message = _message_mapping(item.payload)
        channel = message.get("channel")
        if channel == "subscriptionResponse":
            return
        if channel == "orderUpdates":
            self._apply_order_updates(message.get("data"))
            return
        data = mapping(message.get("data"), f"{channel} data")
        if channel == "l2Book":
            self._book = parse_book_for_symbol(
                data,
                symbol=self._symbol,
                depth_levels=self._depth_levels,
            )
            self._book_received_ns = item.received_ts_ns
        elif channel == "clearinghouseState":
            self._perp_state = data.get("clearinghouseState")
        elif channel == "spotState":
            self._spot_state = data.get("spotState")
        elif channel == "openOrders":
            self._orders = self._parse_orders(data.get("orders"))
        elif channel == "userFills":
            incoming = self._parse_fills(data.get("fills"))
            is_snapshot = _fill_snapshot_flag(data)
            self._fills = incoming if is_snapshot else self._merge_fills(incoming)

    def _apply_order_updates(self, value: object) -> None:
        orders = {order.oid: order for order in self._orders or ()}
        for raw in sequence(value, "stream order updates"):
            update = mapping(raw, "stream order update")
            order_value = mapping(update.get("order"), "stream updated order")
            if order_value.get("coin") != self._symbol:
                continue
            status = text(update.get("status"), "stream order status")
            if status == "open":
                order = _parse_apex_open_update(order_value)
                orders[order.oid] = order
            elif status in _TERMINAL_ORDER_STATUSES:
                oid = positive_integer(order_value.get("oid"), "stream order oid")
                orders.pop(oid, None)
            else:
                raise ApexMMVenueStreamError(
                    f"unsupported venue stream order status: {status}"
                )
        self._orders = tuple(orders.values())

    def _parse_orders(self, value: object) -> tuple[SolOpenOrder, ...]:
        return tuple(
            parse_open_order(item)
            for item in sequence(value, "stream open orders")
            if mapping(item, "stream open order").get("coin") == self._symbol
        )

    def _parse_fills(self, value: object) -> tuple[SolFill, ...]:
        return tuple(
            parse_fill(item)
            for item in sequence(value, "stream fills")
            if mapping(item, "stream fill").get("coin") == self._symbol
        )

    def _merge_fills(self, incoming: tuple[SolFill, ...]) -> tuple[SolFill, ...]:
        by_trade = {fill.trade_id: fill for fill in self._fills or ()}
        by_trade.update((fill.trade_id, fill) for fill in incoming)
        return tuple(by_trade.values())[-_MAX_CACHED_FILLS:]

    def _invalidate(self, reason: str) -> None:
        self._book = None
        self._book_received_ns = None
        self._perp_state = None
        self._spot_state = None
        self._orders = None
        self._fills = None
        self._disconnect_reason = reason


def _subscription_payload(subscription: Mapping[str, str]) -> str:
    return json.dumps(
        {"method": "subscribe", "subscription": subscription},
        separators=(",", ":"),
        sort_keys=True,
    )


def _fill_snapshot_flag(data: Mapping[str, object]) -> bool:
    if "isSnapshot" not in data:
        return False
    return boolean(data.get("isSnapshot"), "userFills isSnapshot")


def _parse_apex_open_update(value: Mapping[str, object]) -> SolOpenOrder:
    """Project the lean live update under the Apex non-trigger quote contract."""
    return SolOpenOrder(
        oid=positive_integer(value.get("oid"), "stream order oid"),
        size=positive_number(value.get("sz"), "stream order size"),
        original_size=positive_number(
            value.get("origSz"),
            "stream order original size",
        ),
        side=text(value.get("side"), "stream order side"),
        reduce_only=False,
        is_trigger=False,
        trigger_price=None,
        order_type="Limit",
        timestamp_ms=nonnegative_integer(
            value.get("timestamp"),
            "stream order timestamp",
        ),
        limit_price=positive_number(
            value.get("limitPx"),
            "stream order limit price",
        ),
    )


def _message_mapping(payload: str | bytes) -> Mapping[str, object]:
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ApexMMVenueStreamError("venue stream returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ApexMMVenueStreamError("venue stream message must be an object")
    return cast(Mapping[str, object], decoded)
