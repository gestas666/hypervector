"""Least-privilege symbol-parameterized Hyperliquid perpetual reader."""

from __future__ import annotations

import logging

from hypervector.data.oxa_api import validate_hip3_symbol
from hypervector.live.hyperliquid_protocol import (
    Hip3MarketFeeMetadata,
    HyperliquidInfoProtocol,
    HyperliquidOrderStatus,
    HyperliquidReadCacheProtocol,
    SolAccountSnapshot,
    SolBookSnapshot,
    SolFill,
    SolFundingPayment,
    SolMarketMetadata,
    SolOpenOrder,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.hyperliquid_hip3_fee_parsing import (
    parse_hip3_market_fee_metadata,
)
from hypervector.live.hyperliquid_perp_parsing import (
    parse_account_mode_for_symbol,
    parse_book_for_symbol,
    parse_funding_for_symbol,
    parse_market_for_symbol,
    parse_mid_for_symbol,
)
from hypervector.live.hyperliquid_sol_account import parse_account_mode
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    mapping,
    parse_fees,
    parse_fill,
    parse_open_order,
    parse_order_status,
    positive_integer,
    price_tick,
    sequence,
    validate_address,
)
from hypervector.live.hyperliquid_user_funding_history import read_user_funding_history
from hypervector.live.sol_order_identity import validate_client_order_id

logger = logging.getLogger(__name__)
# Stable prefix of the warning for a tolerated venue maximum-leverage change.
VENUE_MAX_LEVERAGE_CHANGED = "venue_max_leverage_changed"


class VenueMetadataMismatchError(HyperliquidAdapterError):
    """Venue market metadata contradicts the configured market contract.

    A venue fact such as a changed maximum leverage persists across relaunches, so
    the live boundary refuses the start instead of crashing into a restart loop.
    """


def require_requested_leverage(symbol: str, requested: object) -> int:
    """Return a market's requested leverage, refusing anything but a positive int.

    A malformed value is the caller's error, so callers check it before any read.
    """
    if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
        raise ValueError(f"{symbol} requested leverage must be a positive integer")
    return requested


def venue_max_leverage_refusal(
    symbol: str,
    observed: int,
    *,
    expected: int,
    requested: int | None,
) -> str | None:
    """Return why a venue maximum leverage refuses the start, or None when allowed.

    Without ``requested`` the venue maximum must equal the profile's ``expected``
    value. With the leverage the market will request (rounded up to the venue's
    integer grid), only a venue maximum below it refuses, so the venue is never
    asked for more leverage than it allows.
    """
    if requested is None:
        if observed == expected:
            return None
        return (
            f"{symbol} max leverage mismatch: expected {expected}, observed {observed}"
        )
    if observed >= require_requested_leverage(symbol, requested):
        return None
    return (
        f"{symbol} venue max leverage {observed} is below the requested leverage "
        f"{requested} (profile venue maximum {expected})"
    )


def venue_max_leverage_warning(
    symbol: str,
    observed: int,
    *,
    expected: int,
    requested: int,
) -> str | None:
    """Return the warning for a changed maximum that still allows ``requested``."""
    if observed == expected:
        return None
    return (
        f"{VENUE_MAX_LEVERAGE_CHANGED}: {symbol} venue max leverage {observed} "
        f"differs from the profile's {expected}; the requested leverage "
        f"{requested} is still allowed, so the start continues"
    )


class HyperliquidPerpReader:
    """Expose read-only official-SDK endpoints for one perpetual symbol."""

    def __init__(
        self,
        *,
        info: HyperliquidInfoProtocol,
        account_address: str,
        symbol: str,
        perp_dex: str = "",
    ) -> None:
        self._info = info
        self._address = validate_address(account_address)
        self._symbol, self._perp_dex = _venue_identity(symbol, perp_dex)
        self._market_cache: SolMarketMetadata | None = None
        self._market_metadata_cache: object | None = None
        self._account_mode_cache: str | None = None

    def preflight(
        self,
        *,
        expected_max_leverage: int,
        requested_leverage: int | None = None,
    ) -> SolVenuePreflight:
        """Read metadata, fees, account state, and current mark.

        Without ``requested_leverage`` the venue maximum must equal the expected
        one. With it, only a venue maximum below the requested leverage refuses;
        any other difference is logged as a warning and the preflight continues.
        A malformed requested leverage is refused before any venue read.
        """
        if requested_leverage is not None:
            require_requested_leverage(self._symbol, requested_leverage)
        market = self._market(refresh=True)
        refusal = venue_max_leverage_refusal(
            self._symbol,
            market.max_leverage,
            expected=expected_max_leverage,
            requested=requested_leverage,
        )
        if refusal is not None:
            raise VenueMetadataMismatchError(refusal)
        if requested_leverage is not None:
            warning = venue_max_leverage_warning(
                self._symbol,
                market.max_leverage,
                expected=expected_max_leverage,
                requested=requested_leverage,
            )
            if warning is not None:
                logger.warning(warning)
        mode = self.account_abstraction_mode(refresh=True)
        account = self._account_snapshot(mode)
        mark = parse_mid_for_symbol(
            self._info.all_mids(self._perp_dex),
            self._symbol,
        )
        return SolVenuePreflight(
            market=market,
            mark_price=mark,
            price_tick=price_tick(mark, market.size_decimals),
            size_step=10.0 ** (-market.size_decimals),
            fees=parse_fees(self._info.user_fees(self._address)),
            account_value_usd=account.account_value_usd,
            withdrawable_usd=account.withdrawable_usd,
            position=account.position,
            account_abstraction_mode=mode,
            hip3_fee_metadata=(self.hip3_fee_metadata() if self._perp_dex else None),
        )

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        """Return one strict public L2 snapshot."""
        return parse_book_for_symbol(
            self._info.l2_snapshot(self._symbol),
            symbol=self._symbol,
            depth_levels=depth_levels,
        )

    def hip3_fee_metadata(self) -> Hip3MarketFeeMetadata:
        """Return exact point-in-time fee modifiers for this HIP-3 market."""
        if not self._perp_dex:
            raise HyperliquidAdapterError(
                "HIP-3 fee metadata requires a namespaced perpetual"
            )
        if self._market_metadata_cache is None:
            self._market(refresh=True)
        return parse_hip3_market_fee_metadata(
            metadata=self._market_metadata_cache,
            dexes=self._info.perp_dexs(),
            symbol=self._symbol,
            perp_dex=self._perp_dex,
        )

    def account_abstraction_mode(self, *, refresh: bool = False) -> str:
        """Return the validated venue account balance model."""
        if self._account_mode_cache is None or refresh:
            self._account_mode_cache = parse_account_mode(
                self._info.query_user_abstraction_state(self._address)
            )
        return self._account_mode_cache

    def account_snapshot(self) -> SolAccountSnapshot:
        """Return account totals and exposure for only this symbol."""
        return self._account_snapshot(self.account_abstraction_mode())

    def _account_snapshot(self, mode: str) -> SolAccountSnapshot:
        return parse_account_mode_for_symbol(
            mode=mode,
            perp_state=self._info.user_state(self._address, self._perp_dex),
            spot_state=(
                self._info.spot_user_state(self._address)
                if mode == "unifiedAccount"
                else None
            ),
            symbol=self._symbol,
        )

    def open_orders(self) -> tuple[SolOpenOrder, ...]:
        """Return venue-reported open orders for only this symbol."""
        raw = sequence(
            self._info.frontend_open_orders(self._address, self._perp_dex),
            "open orders",
        )
        return tuple(
            parse_open_order(item)
            for item in raw
            if mapping(item, "open order").get("coin") == self._symbol
        )

    def fills(self) -> tuple[SolFill, ...]:
        """Return recent account fills for only this symbol."""
        raw = sequence(self._info.user_fills(self._address), "user fills")
        return tuple(
            parse_fill(item)
            for item in raw
            if mapping(item, "fill").get("coin") == self._symbol
        )

    def reconcile(self) -> SolReconciliationSnapshot:
        """Return account, open orders, and fills from venue truth."""
        return SolReconciliationSnapshot(
            account=self.account_snapshot(),
            open_orders=self.open_orders(),
            fills=self.fills(),
        )

    def invalidate_reconciliation_cache(self) -> None:
        """Discard shared cached account truth when the reader has a cache."""
        if isinstance(self._info, HyperliquidReadCacheProtocol):
            self._info.invalidate_shared_reads()

    def funding_payments(
        self,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[SolFundingPayment, ...]:
        """Return exact bounded funding rows for only this symbol."""
        response = read_user_funding_history(
            self._info, self._address, start_time_ms, end_time_ms
        )
        return parse_funding_for_symbol(response, self._symbol)

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        """Return one exact venue order state."""
        order_id = positive_integer(oid, "oid")
        response = self._info.query_order_by_oid(self._address, order_id)
        return parse_order_status(response, expected_oid=order_id)

    def order_status_by_client_id(self, client_order_id: str) -> HyperliquidOrderStatus:
        """Return one exact order using its durable client identity."""
        identity = validate_client_order_id(client_order_id)
        response = self._info.query_order_by_oid(self._address, identity)
        return parse_order_status(response, expected_client_order_id=identity)

    def _market(self, *, refresh: bool = False) -> SolMarketMetadata:
        if self._market_cache is None or refresh:
            self._market_metadata_cache = self._info.meta(self._perp_dex)
            self._market_cache = parse_market_for_symbol(
                self._market_metadata_cache,
                self._symbol,
            )
        return self._market_cache


def _venue_identity(symbol: str, perp_dex: str) -> tuple[str, str]:
    normalized_symbol = symbol.strip()
    normalized_dex = perp_dex.strip()
    if ":" not in normalized_symbol and not normalized_dex:
        return normalized_symbol, normalized_dex
    try:
        symbol_dex, _ = validate_hip3_symbol(normalized_symbol)
    except ValueError as exc:
        raise HyperliquidAdapterError(
            "perpetual namespace identity is invalid"
        ) from exc
    if symbol_dex != normalized_dex:
        raise HyperliquidAdapterError("perpetual namespace does not match symbol")
    return normalized_symbol, normalized_dex
