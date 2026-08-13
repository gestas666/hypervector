"""Least-privilege Hyperliquid SOL account and venue reader."""

from __future__ import annotations

import logging

from hypervector.live.hyperliquid_protocol import (
    HyperliquidInfoProtocol,
    HyperliquidOrderStatus,
    SolAccountSnapshot,
    SolBookSnapshot,
    SolFill,
    SolFundingPayment,
    SolMarketMetadata,
    SolOpenOrder,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.hyperliquid_sol_parsing import (
    SOL_SYMBOL,
    HyperliquidAdapterError,
    mapping,
    nonnegative_integer,
    parse_fees,
    parse_fill,
    parse_funding_payments,
    parse_l2_book,
    parse_market,
    parse_open_order,
    parse_order_status,
    parse_sol_mid,
    positive_integer,
    price_tick,
    sequence,
    validate_address,
)
from hypervector.live.hyperliquid_sol_account import (
    parse_account_for_mode,
    parse_account_mode,
)
from hypervector.live.sol_order_identity import validate_client_order_id

logger = logging.getLogger(__name__)


class SolHyperliquidReader:
    """Expose only read-only SOL endpoints from the official SDK Info client."""

    def __init__(
        self,
        *,
        info: HyperliquidInfoProtocol,
        account_address: str,
    ) -> None:
        self._info = info
        self._address = validate_address(account_address)
        self._market_cache: SolMarketMetadata | None = None

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        """Read and validate SOL metadata, fees, and clearinghouse state."""
        market = self._market(refresh=True)
        if market.max_leverage != expected_max_leverage:
            raise HyperliquidAdapterError(
                "SOL venue max leverage mismatch: "
                f"expected {expected_max_leverage}, observed {market.max_leverage}"
            )
        fees = parse_fees(self._info.user_fees(self._address))
        account_mode = self.account_abstraction_mode()
        account = self._account_snapshot(account_mode)
        mark_price = parse_sol_mid(self._info.all_mids())
        result = SolVenuePreflight(
            market=market,
            mark_price=mark_price,
            price_tick=price_tick(mark_price, market.size_decimals),
            size_step=10.0 ** (-market.size_decimals),
            fees=fees,
            account_value_usd=account.account_value_usd,
            withdrawable_usd=account.withdrawable_usd,
            position=account.position,
            account_abstraction_mode=account_mode,
        )
        logger.info(
            "hyperliquid_sol_preflight size_step=%s price_tick=%s "
            "max_leverage=%s maker_rate=%s taker_rate=%s",
            result.size_step,
            result.price_tick,
            result.market.max_leverage,
            result.fees.maker_rate,
            result.fees.taker_rate,
        )
        return result

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        """Return a strict read-only SOL L2 snapshot for telemetry."""
        return parse_l2_book(
            self._info.l2_snapshot(SOL_SYMBOL),
            depth_levels=depth_levels,
        )

    def account_snapshot(self) -> SolAccountSnapshot:
        """Return account equity and SOL exposure under the venue balance mode."""
        return self._account_snapshot(self.account_abstraction_mode())

    def account_abstraction_mode(self) -> str:
        """Return the validated venue balance model for the configured account."""
        return parse_account_mode(
            self._info.query_user_abstraction_state(self._address)
        )

    def _account_snapshot(self, mode: str) -> SolAccountSnapshot:
        perp_state = self._info.user_state(self._address)
        spot_state = (
            self._info.spot_user_state(self._address)
            if mode == "unifiedAccount"
            else None
        )
        return parse_account_for_mode(
            mode=mode,
            perp_state=perp_state,
            spot_state=spot_state,
        )

    def open_orders(self) -> tuple[SolOpenOrder, ...]:
        """Return venue-reported SOL open orders."""
        raw = sequence(
            self._info.frontend_open_orders(self._address),
            "frontend open orders",
        )
        return tuple(
            parse_open_order(item)
            for item in raw
            if mapping(item, "open order").get("coin") == SOL_SYMBOL
        )

    def fills(self) -> tuple[SolFill, ...]:
        """Return venue-reported recent SOL fills."""
        raw = sequence(self._info.user_fills(self._address), "user fills")
        return tuple(
            parse_fill(item)
            for item in raw
            if mapping(item, "fill").get("coin") == SOL_SYMBOL
        )

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        """Read and normalize one exact venue order status."""
        order_id = positive_integer(oid, "oid")
        response = self._info.query_order_by_oid(self._address, order_id)
        return parse_order_status(response, expected_oid=order_id)

    def order_status_by_client_id(
        self,
        client_order_id: str,
    ) -> HyperliquidOrderStatus:
        """Read and identity-check one order by its durable client identity."""
        identity = validate_client_order_id(client_order_id)
        response = self._info.query_order_by_oid(self._address, identity)
        return parse_order_status(
            response,
            expected_client_order_id=identity,
        )

    def funding_payments(
        self,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[SolFundingPayment, ...]:
        """Return exact SOL funding payments from the user ledger."""
        start = nonnegative_integer(start_time_ms, "funding start_time_ms")
        end = nonnegative_integer(end_time_ms, "funding end_time_ms")
        if end < start:
            raise HyperliquidAdapterError("funding end_time_ms must not precede start")
        response = self._info.user_funding_history(
            self._address,
            startTime=start,
            endTime=end,
        )
        return parse_funding_payments(response)

    def reconcile(self) -> SolReconciliationSnapshot:
        """Read authoritative account, open-order, and fill state."""
        return SolReconciliationSnapshot(
            account=self.account_snapshot(),
            open_orders=self.open_orders(),
            fills=self.fills(),
        )

    def verify_flat(self) -> bool:
        """Return true only if venue exposure and all SOL open orders are absent."""
        return self.reconcile().is_flat

    def _market(self, *, refresh: bool = False) -> SolMarketMetadata:
        if self._market_cache is None or refresh:
            self._market_cache = parse_market(self._info.meta())
        return self._market_cache
