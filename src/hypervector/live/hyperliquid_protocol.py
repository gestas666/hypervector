"""Typed boundary contracts for the official Hyperliquid SDK."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SolMarketMetadata:
    """Venue precision and leverage limits for SOL perpetuals."""

    symbol: str
    size_decimals: int
    max_leverage: int


@dataclass(frozen=True)
class HyperliquidFeeSchedule:
    """Account-specific maker and taker fee rates."""

    maker_rate: float
    taker_rate: float
    active_referral_discount: float = 0.0


@dataclass(frozen=True)
class Hip3MarketFeeMetadata:
    """Venue inputs that modify account base rates for one HIP-3 market."""

    deployer_fee_scale: float | None
    growth_mode: bool | None
    collateral_token_index: int


@dataclass(frozen=True)
class SolPositionSnapshot:
    """Venue-authoritative one-way SOL position state."""

    size_signed: float
    entry_price: float | None
    liquidation_price: float | None
    margin_used_usd: float
    position_value_usd: float
    unrealized_pnl_usd: float
    leverage_type: str | None
    leverage: int | None


@dataclass(frozen=True)
class SolAccountSnapshot:
    """Clearinghouse values and the current SOL position."""

    account_value_usd: float
    withdrawable_usd: float
    total_margin_used_usd: float
    total_notional_position_usd: float
    position: SolPositionSnapshot
    balance_source: str | None = None


@dataclass(frozen=True)
class SolOpenOrder:
    """One venue-reported open SOL order."""

    oid: int
    size: float
    original_size: float
    side: str
    reduce_only: bool
    is_trigger: bool
    trigger_price: float | None
    order_type: str
    timestamp_ms: int
    limit_price: float | None = None


@dataclass(frozen=True)
class SolFill:
    """One venue-reported SOL fill with fee and exchange time."""

    oid: int
    price: float
    size: float
    side: str
    timestamp_ms: int
    fee_usd: float
    fee_token: str
    closed_pnl_usd: float
    crossed: bool
    direction: str
    transaction_hash: str
    trade_id: int


@dataclass(frozen=True)
class SolFundingPayment:
    """One exact SOL funding ledger update for the configured account."""

    timestamp_ms: int
    usdc_delta: float
    position_size_signed: float
    funding_rate: float
    transaction_hash: str


@dataclass(frozen=True)
class SolBookLevel:
    """One price level from the venue L2 snapshot."""

    price: float
    size: float
    order_count: int


@dataclass(frozen=True)
class SolBookSnapshot:
    """Read-only SOL L2 depth and directly derived pressure metrics."""

    exchange_timestamp_ms: int
    bids: tuple[SolBookLevel, ...]
    asks: tuple[SolBookLevel, ...]
    mid_price: float
    spread_bps: float
    bid_depth: float
    ask_depth: float
    order_pressure: float


@dataclass(frozen=True)
class HyperliquidOrderAck:
    """Normalized exchange acknowledgement for one exact order operation."""

    accepted: bool
    oid: int | None
    status: str
    filled_size: float | None = None
    average_price: float | None = None
    error: str | None = None
    client_order_id: str | None = None
    recovered_after_transport_error: bool = False
    venue_timestamp_ms: int | None = None
    recovered_after_restart: bool = False


@dataclass(frozen=True)
class HyperliquidPostOnlyOrder:
    """One client-identified opening leg in a single post-only batch."""

    side: str
    requested_notional_usd: float
    limit_price: float
    client_order_id: str


@dataclass(frozen=True)
class HyperliquidOrderStatus:
    """Normalized order-status response from the info endpoint."""

    oid: int
    symbol: str
    status: str
    size: float
    status_timestamp_ms: int
    client_order_id: str | None = None


@dataclass(frozen=True)
class SolVenuePreflight:
    """Read-only venue and account facts required before live arming."""

    market: SolMarketMetadata
    mark_price: float
    price_tick: float
    size_step: float
    fees: HyperliquidFeeSchedule
    account_value_usd: float
    withdrawable_usd: float
    position: SolPositionSnapshot
    account_abstraction_mode: str = "disabled"
    hip3_fee_metadata: Hip3MarketFeeMetadata | None = None


@dataclass(frozen=True)
class SolReconciliationSnapshot:
    """Authoritative SOL account, open-order, and fill state."""

    account: SolAccountSnapshot
    open_orders: tuple[SolOpenOrder, ...]
    fills: tuple[SolFill, ...]

    @property
    def position(self) -> SolPositionSnapshot:
        """Return the reconciled SOL position."""
        return self.account.position

    @property
    def is_flat(self) -> bool:
        """Return true only when exposure and every SOL open order are absent."""
        return self.position.size_signed == 0.0 and not self.open_orders


@runtime_checkable
class HyperliquidReadCacheProtocol(Protocol):
    """Optional cache control exposed by shared serialized readers."""

    def invalidate_shared_reads(self) -> None:
        """Discard coalesced account responses before a consistency retry."""
        ...


@runtime_checkable
class HyperliquidInfoProtocol(Protocol):
    """Read-only subset of ``hyperliquid.info.Info`` used by the adapter."""

    def meta(self, dex: str = "") -> object:
        """Return perpetual market metadata."""
        ...

    def perp_dexs(self) -> object:
        """Return active HIP-3 deployer metadata."""
        ...

    def user_fees(self, address: str) -> object:
        """Return account-specific fee rates."""
        ...

    def all_mids(self, dex: str = "") -> object:
        """Return current midpoint prices by perpetual symbol."""
        ...

    def l2_snapshot(self, name: str) -> object:
        """Return the current L2 book for one perpetual symbol."""
        ...

    def user_state(self, address: str, dex: str = "") -> object:
        """Return clearinghouse account and position state."""
        ...

    def query_user_abstraction_state(self, address: str) -> object:
        """Return the account's balance-abstraction mode."""
        ...

    def spot_user_state(self, address: str) -> object:
        """Return spot balances and holds for unified accounts."""
        ...

    def user_role(self, address: str) -> object:
        """Return whether an address is a user, agent, vault, or subaccount."""
        ...

    def frontend_open_orders(self, address: str, dex: str = "") -> object:
        """Return open orders including trigger metadata."""
        ...

    def user_fills(self, address: str) -> object:
        """Return recent account fills."""
        ...

    def query_order_by_oid(self, user: str, oid: int | str) -> object:
        """Return one order by venue ID or 16-byte client-order ID."""
        ...

    def user_funding_history(
        self,
        user: str,
        startTime: int,
        endTime: int | None = None,
    ) -> object:
        """Return exact user funding ledger updates in a bounded interval."""
        ...


@runtime_checkable
class HyperliquidExchangeProtocol(Protocol):
    """Narrow authenticated subset of ``hyperliquid.exchange.Exchange``."""

    def update_leverage(
        self,
        leverage: int,
        name: str,
        is_cross: bool = True,
    ) -> object:
        """Set leverage and isolated/cross mode for one market."""
        ...

    def market_open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Submit an IOC market-style opening order."""
        ...

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: object,
        reduce_only: bool = False,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Submit an explicit limit or trigger order."""
        ...

    def bulk_orders(
        self,
        order_requests: list[object],
        builder: object | None = None,
        grouping: str = "na",
    ) -> object:
        """Submit multiple explicit orders in one signed exchange action."""
        ...

    def cancel(self, name: str, oid: int) -> object:
        """Cancel exactly one order by venue order ID."""
        ...

    def market_close(
        self,
        coin: str,
        sz: float | None = None,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Submit the SDK's reduce-only IOC close operation."""
        ...


@runtime_checkable
class SolLiveAdapterProtocol(Protocol):
    """Venue operations required by the deterministic SOL lifecycle."""

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        """Return validated venue and account facts."""
        ...

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        """Return read-only venue L2 telemetry."""
        ...

    def configure_isolated_leverage(self, leverage: int) -> None:
        """Configure explicit isolated leverage."""
        ...

    def submit_entry(
        self,
        *,
        side: str,
        requested_notional_usd: float,
        mark_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Submit one bounded opening order."""
        ...

    def place_protective_stop(
        self,
        *,
        position_size_signed: float,
        trigger_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Place one venue-native reduce-only stop."""
        ...

    def submit_target(
        self,
        *,
        position_size_signed: float,
        limit_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Place one reduce-only post-only target."""
        ...

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        """Cancel exactly one order."""
        ...

    def close_position(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Submit a reduce-only close for reconciled exposure."""
        ...

    def reconcile(self) -> SolReconciliationSnapshot:
        """Return authoritative account, order, and fill state."""
        ...

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        """Return one exact order's status."""
        ...

    def order_status_by_client_id(
        self,
        client_order_id: str,
    ) -> HyperliquidOrderStatus:
        """Return status for one exact durable client-order identity."""
        ...

    def funding_payments(
        self,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[SolFundingPayment, ...]:
        """Return exact account funding payments for SOL."""
        ...
