"""Narrow, fail-closed Hyperliquid adapter for the SOL live canary."""

from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from hyperliquid.utils.types import Cloid  # type: ignore[import-untyped]

from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
    HyperliquidOrderAck,
)
from hypervector.live.hyperliquid_sol_parsing import (
    SOL_SYMBOL,
    HyperliquidAdapterError,
    entry_is_buy,
    nonnegative_finite,
    nonzero_finite,
    normalize_perp_price,
    parse_cancel_ack,
    parse_order_ack,
    positive_finite,
    positive_integer,
    require_ok,
)
from hypervector.live.hyperliquid_sol_reader import SolHyperliquidReader
from hypervector.live.sol_order_identity import validate_client_order_id
from hypervector.live.sol_order_transport import (
    call_ambiguous_cancel_mutation,
    call_ambiguous_order_mutation,
)


class SolHyperliquidAdapter(SolHyperliquidReader):
    """Translate SOL canary operations into a minimal official-SDK surface."""

    def __init__(
        self,
        *,
        info: HyperliquidInfoProtocol,
        exchange: HyperliquidExchangeProtocol,
        account_address: str,
        max_notional_usd: float,
        slippage_fraction: float,
    ) -> None:
        super().__init__(info=info, account_address=account_address)
        self._exchange = exchange
        self._max_notional_usd = positive_finite(
            max_notional_usd,
            "max_notional_usd",
        )
        slippage = nonnegative_finite(slippage_fraction, "slippage_fraction")
        if slippage > 0.05:
            raise HyperliquidAdapterError("slippage_fraction must not exceed 0.05")
        self._slippage_fraction = slippage

    @property
    def symbol(self) -> str:
        """Return the one perpetual symbol owned by this adapter."""
        return SOL_SYMBOL

    def configure_isolated_leverage(self, leverage: int) -> None:
        """Set explicit isolated leverage and validate venue acknowledgement."""
        if isinstance(leverage, bool) or leverage <= 0:
            raise HyperliquidAdapterError("leverage must be a positive integer")
        market = self._market()
        if leverage > market.max_leverage:
            raise HyperliquidAdapterError(
                f"leverage {leverage} exceeds SOL venue max {market.max_leverage}"
            )
        response = self._exchange.update_leverage(
            leverage,
            SOL_SYMBOL,
            is_cross=False,
        )
        require_ok(response, "isolated leverage update")

    def submit_entry(
        self,
        *,
        side: str,
        requested_notional_usd: float,
        mark_price: float,
        client_order_id: str,
        entry_deadline: EntrySubmissionDeadline | None = None,
    ) -> HyperliquidOrderAck:
        """Submit one cap-checked, lot-rounded SOL opening order."""
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
            operation="entry",
            client_order_id=identity,
            mutation=lambda: self._exchange.market_open(
                SOL_SYMBOL,
                entry_is_buy(side),
                size,
                px=price,
                slippage=self._slippage_fraction,
                cloid=Cloid.from_str(identity),
            ),
        )
        return replace(
            parse_order_ack(response, operation="entry"),
            client_order_id=identity,
        )

    def place_protective_stop(
        self,
        *,
        position_size_signed: float,
        trigger_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Place a reduce-only market trigger for reconciled SOL exposure."""
        position_size = nonzero_finite(position_size_signed, "position_size_signed")
        price = normalize_perp_price(trigger_price, self._market().size_decimals)
        size = self._round_size_down(abs(position_size))
        identity = validate_client_order_id(client_order_id)
        response = call_ambiguous_order_mutation(
            operation="protective_stop",
            client_order_id=identity,
            mutation=lambda: self._exchange.order(
                SOL_SYMBOL,
                position_size < 0.0,
                size,
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

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        """Cancel exactly one SOL order; broad cancel is intentionally absent."""
        order_id = positive_integer(oid, "oid")
        response = call_ambiguous_cancel_mutation(
            operation="cancel_order",
            oid=order_id,
            mutation=lambda: self._exchange.cancel(SOL_SYMBOL, order_id),
        )
        return parse_cancel_ack(response, order_id)

    def close_position(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Submit the SDK's reduce-only market close for reconciled exposure."""
        position_size = nonzero_finite(position_size_signed, "position_size_signed")
        price = positive_finite(mark_price, "mark_price")
        size = self._round_size_down(abs(position_size))
        identity = validate_client_order_id(client_order_id)
        response = call_ambiguous_order_mutation(
            operation="reduce_only_close",
            client_order_id=identity,
            mutation=lambda: self._exchange.market_close(
                SOL_SYMBOL,
                sz=size,
                px=price,
                slippage=self._slippage_fraction,
                cloid=Cloid.from_str(identity),
            ),
        )
        return replace(
            parse_order_ack(response, operation="reduce-only close"),
            client_order_id=identity,
        )

    def _round_size_down(self, size: float) -> float:
        market = self._market()
        quantum = Decimal(1).scaleb(-market.size_decimals)
        try:
            rounded = Decimal(str(size)).quantize(quantum, rounding=ROUND_DOWN)
        except InvalidOperation as exc:
            raise HyperliquidAdapterError("SOL size could not be rounded") from exc
        if rounded <= 0:
            raise HyperliquidAdapterError("SOL size rounds to zero at venue precision")
        return float(rounded)
