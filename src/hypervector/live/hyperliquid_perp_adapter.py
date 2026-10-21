"""Symbol-parameterized perpetual execution adapter for the per-asset live engine."""

from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from hyperliquid.utils.types import Cloid  # type: ignore[import-untyped]

from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.hyperliquid_perp_reader import HyperliquidPerpReader
from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
    HyperliquidOrderAck,
    HyperliquidPostOnlyOrder,
)
from hypervector.live.hyperliquid_parsing import (
    HyperliquidAdapterError,
    nonnegative_finite,
    nonzero_finite,
    normalize_perp_price,
    parse_cancel_ack,
    parse_order_ack,
    parse_order_acks,
    positive_finite,
    positive_integer,
    require_ok,
)
from hypervector.live.perp_venue_identity import parse_perp_venue_identity
from hypervector.live.asset_order_identity import validate_client_order_id
from hypervector.live.asset_order_transport import (
    call_ambiguous_batch_order_mutation,
    call_ambiguous_cancel_mutation,
    call_ambiguous_order_mutation,
)


class HyperliquidPerpAdapter(HyperliquidPerpReader):
    """Translate one symbol's protected order lifecycle into official SDK calls."""

    def __init__(
        self,
        *,
        info: HyperliquidInfoProtocol,
        exchange: HyperliquidExchangeProtocol,
        account_address: str,
        symbol: str,
        max_notional_usd: float,
        slippage_fraction: float,
        entry_slippage_fraction: float | None = None,
        perp_dex: str = "",
    ) -> None:
        try:
            identity = parse_perp_venue_identity(symbol)
        except ValueError as exc:
            raise HyperliquidAdapterError(str(exc)) from exc
        if identity.perp_dex != perp_dex.strip():
            raise HyperliquidAdapterError(
                "symbol namespace and authenticated perp_dex must match"
            )
        super().__init__(
            info=info,
            account_address=account_address,
            symbol=identity.symbol,
            perp_dex=identity.perp_dex,
        )
        self._exchange = exchange
        self._max_notional_usd = positive_finite(max_notional_usd, "max_notional_usd")
        slippage = nonnegative_finite(slippage_fraction, "slippage_fraction")
        if slippage > 0.05:
            raise HyperliquidAdapterError("slippage_fraction must not exceed 0.05")
        self._slippage_fraction = slippage
        entry_slippage = (
            slippage
            if entry_slippage_fraction is None
            else nonnegative_finite(
                entry_slippage_fraction,
                "entry_slippage_fraction",
            )
        )
        if entry_slippage > 0.05:
            raise HyperliquidAdapterError(
                "entry_slippage_fraction must not exceed 0.05"
            )
        self._entry_slippage_fraction = entry_slippage

    @property
    def symbol(self) -> str:
        """Return the one perpetual symbol owned by this adapter."""
        return self._symbol

    @property
    def perp_dex(self) -> str:
        """Return the exact builder-perp namespace used by this adapter."""
        return self._perp_dex

    @property
    def slippage_fraction(self) -> float:
        """Return the configured reduce-only IOC price-protection fraction."""
        return self._slippage_fraction

    @property
    def entry_slippage_fraction(self) -> float:
        """Return the configured opening IOC price-protection fraction."""
        return self._entry_slippage_fraction

    def configure_isolated_leverage(self, leverage: int) -> None:
        """Set explicit isolated leverage and validate acknowledgement."""
        if isinstance(leverage, bool) or leverage <= 0:
            raise HyperliquidAdapterError("leverage must be a positive integer")
        market = self._market()
        if leverage > market.max_leverage:
            raise HyperliquidAdapterError(
                f"leverage {leverage} exceeds {self.symbol} venue max "
                f"{market.max_leverage}"
            )
        response = self._exchange.update_leverage(
            leverage,
            self.symbol,
            is_cross=False,
        )
        require_ok(response, "isolated leverage update")

    def submit_entry(
        self,
        *,
        side: str,
        requested_notional_usd: float,
        limit_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Submit one cap-checked post-only opening limit."""
        notional = positive_finite(requested_notional_usd, "requested_notional_usd")
        if notional > self._max_notional_usd + 1e-12:
            raise HyperliquidAdapterError(
                f"requested notional {notional:g} exceeds cap {self._max_notional_usd:g}"
            )
        price = positive_finite(limit_price, "limit_price")
        return self._submit_limit(
            is_buy=_entry_is_buy(side),
            size=self._round_size_down(notional / price),
            limit_price=price,
            reduce_only=False,
            client_order_id=client_order_id,
            operation="post-only entry",
        )

    def submit_target(
        self,
        *,
        position_size_signed: float,
        limit_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Submit one reduce-only post-only target for reconciled exposure."""
        position = nonzero_finite(position_size_signed, "position_size_signed")
        return self._submit_limit(
            is_buy=position < 0.0,
            size=self._round_size_down(abs(position)),
            limit_price=positive_finite(limit_price, "limit_price"),
            reduce_only=True,
            client_order_id=client_order_id,
            operation="post-only target",
        )

    def submit_post_only_batch(
        self,
        orders: tuple[HyperliquidPostOnlyOrder, ...],
    ) -> tuple[HyperliquidOrderAck, ...]:
        """Submit one or two opening quotes in one signed exchange action."""
        if not 1 <= len(orders) <= 2:
            raise HyperliquidAdapterError(
                "post-only quote batch must contain one or two orders"
            )
        requests: list[object] = []
        identities: list[str] = []
        for order in orders:
            notional = positive_finite(
                order.requested_notional_usd,
                "requested_notional_usd",
            )
            if notional > self._max_notional_usd + 1e-12:
                raise HyperliquidAdapterError(
                    f"requested notional {notional:g} exceeds cap "
                    f"{self._max_notional_usd:g}"
                )
            price = positive_finite(order.limit_price, "limit_price")
            identity = validate_client_order_id(order.client_order_id)
            identities.append(identity)
            requests.append(
                {
                    "coin": self.symbol,
                    "is_buy": _entry_is_buy(order.side),
                    "sz": self._round_size_down(notional / price),
                    "limit_px": normalize_perp_price(
                        price,
                        self._market().size_decimals,
                    ),
                    "order_type": {"limit": {"tif": "Alo"}},
                    "reduce_only": False,
                    "cloid": Cloid.from_str(identity),
                }
            )
        durable_ids = tuple(identities)
        if len(set(durable_ids)) != len(durable_ids):
            raise HyperliquidAdapterError("post-only batch client IDs must be unique")
        response = call_ambiguous_batch_order_mutation(
            operation="post-only quote batch",
            client_order_ids=durable_ids,
            mutation=lambda: self._exchange.bulk_orders(requests, grouping="na"),
        )
        acknowledgements = parse_order_acks(
            response,
            operation="post-only quote batch",
            expected_count=len(requests),
        )
        return tuple(
            replace(ack, client_order_id=identity)
            for ack, identity in zip(acknowledgements, durable_ids, strict=True)
        )

    def submit_market_entry(
        self,
        *,
        side: str,
        requested_notional_usd: float,
        mark_price: float,
        client_order_id: str,
        entry_deadline: EntrySubmissionDeadline | None = None,
    ) -> HyperliquidOrderAck:
        """Submit one cap-checked, lot-rounded market entry."""
        notional = positive_finite(requested_notional_usd, "requested_notional_usd")
        if notional > self._max_notional_usd + 1e-12:
            raise HyperliquidAdapterError(
                f"requested notional {notional:g} exceeds cap {self._max_notional_usd:g}"
            )
        price = positive_finite(mark_price, "mark_price")
        size = self._round_size_down(notional / price)
        identity = validate_client_order_id(client_order_id)
        if entry_deadline is not None:
            entry_deadline.check("sdk_dispatch")
        response = call_ambiguous_order_mutation(
            operation="market_entry",
            client_order_id=identity,
            mutation=lambda: self._exchange.market_open(
                self.symbol,
                _entry_is_buy(side),
                size,
                px=price,
                slippage=self._entry_slippage_fraction,
                cloid=Cloid.from_str(identity),
            ),
        )
        return replace(
            parse_order_ack(response, operation="market entry"),
            client_order_id=identity,
        )

    def normalize_trigger_price(self, trigger_price: float) -> float:
        """Return the trigger exactly as this adapter's stop orders put it on the wire.

        It is the official SDK's perp price rounding over the cached market
        metadata, so comparing a target with a venue trigger through it compares
        both on the venue grid. It never mutates venue state.
        """
        return normalize_perp_price(trigger_price, self._market().size_decimals)

    def place_protective_stop(
        self,
        *,
        position_size_signed: float,
        trigger_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Place one reduce-only market trigger for reconciled exposure."""
        position = nonzero_finite(position_size_signed, "position_size_signed")
        price = self.normalize_trigger_price(trigger_price)
        identity = validate_client_order_id(client_order_id)
        response = call_ambiguous_order_mutation(
            operation="protective_stop",
            client_order_id=identity,
            mutation=lambda: self._exchange.order(
                self.symbol,
                position < 0.0,
                self._round_size_down(abs(position)),
                price,
                order_type={
                    "trigger": {
                        "triggerPx": price,
                        "isMarket": True,
                        "tpsl": "sl",
                    }
                },
                reduce_only=True,
                cloid=Cloid.from_str(identity),
            ),
        )
        return replace(
            parse_order_ack(response, operation="protective stop"),
            client_order_id=identity,
        )

    def modify_protective_stop(
        self,
        *,
        oid: int,
        position_size_signed: float,
        trigger_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Replace one owned reduce-only stop with a new trigger in a single venue action."""
        order_id = positive_integer(oid, "oid")
        position = nonzero_finite(position_size_signed, "position_size_signed")
        price = self.normalize_trigger_price(trigger_price)
        identity = validate_client_order_id(client_order_id)
        response = call_ambiguous_order_mutation(
            operation="raise_protective_stop",
            client_order_id=identity,
            mutation=lambda: self._exchange.modify_order(
                order_id,
                self.symbol,
                position < 0.0,
                self._round_size_down(abs(position)),
                price,
                {
                    "trigger": {
                        "triggerPx": price,
                        "isMarket": True,
                        "tpsl": "sl",
                    }
                },
                reduce_only=True,
                cloid=Cloid.from_str(identity),
            ),
        )
        return replace(
            parse_order_ack(response, operation="protective stop raise"),
            client_order_id=identity,
        )

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        """Cancel exactly one order."""
        order_id = positive_integer(oid, "oid")
        response = call_ambiguous_cancel_mutation(
            operation="cancel_order",
            oid=order_id,
            mutation=lambda: self._exchange.cancel(self.symbol, order_id),
        )
        return parse_cancel_ack(response, order_id)

    def close_position(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Submit the SDK reduce-only IOC close for a maximum-hold exit."""
        position = nonzero_finite(position_size_signed, "position_size_signed")
        identity = validate_client_order_id(client_order_id)
        response = call_ambiguous_order_mutation(
            operation="maximum_hold_close",
            client_order_id=identity,
            mutation=lambda: self._exchange.market_close(
                self.symbol,
                sz=self._round_size_down(abs(position)),
                px=positive_finite(mark_price, "mark_price"),
                slippage=self._slippage_fraction,
                cloid=Cloid.from_str(identity),
            ),
        )
        return replace(
            parse_order_ack(response, operation="maximum-hold close"),
            client_order_id=identity,
        )

    def _submit_limit(
        self,
        *,
        is_buy: bool,
        size: float,
        limit_price: float,
        reduce_only: bool,
        client_order_id: str,
        operation: str,
    ) -> HyperliquidOrderAck:
        market = self._market()
        price = normalize_perp_price(limit_price, market.size_decimals)
        identity = validate_client_order_id(client_order_id)
        response = call_ambiguous_order_mutation(
            operation=operation,
            client_order_id=identity,
            mutation=lambda: self._exchange.order(
                self.symbol,
                is_buy,
                size,
                price,
                order_type={"limit": {"tif": "Alo"}},
                reduce_only=reduce_only,
                cloid=Cloid.from_str(identity),
            ),
        )
        return replace(
            parse_order_ack(response, operation=operation),
            client_order_id=identity,
        )

    def _round_size_down(self, size: float) -> float:
        quantum = Decimal(1).scaleb(-self._market().size_decimals)
        try:
            rounded = Decimal(str(size)).quantize(quantum, rounding=ROUND_DOWN)
        except InvalidOperation as exc:
            raise HyperliquidAdapterError(
                f"{self.symbol} size could not be rounded"
            ) from exc
        if rounded <= 0:
            raise HyperliquidAdapterError(f"{self.symbol} size rounds to zero")
        return float(rounded)


def _entry_is_buy(side: str) -> bool:
    normalized = side.strip().lower()
    if normalized in {"long", "buy", "b"}:
        return True
    if normalized in {"short", "sell", "s"}:
        return False
    raise HyperliquidAdapterError(f"unsupported entry side: {side!r}")
