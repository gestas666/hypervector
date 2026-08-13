"""Fail-closed construction of the official-SDK Apex MM adapter."""

from __future__ import annotations

from collections.abc import Mapping
import os

from hypervector.data.hl_ws_feed import HyperliquidWebSocketFeed
from hypervector.live.apex_mm_live_config import ApexMMLiveConfig
from hypervector.live.apex_mm_streaming_venue import ApexMMStreamingVenue
from hypervector.live.apex_mm_venue_stream import (
    ApexMMVenueStream,
    apex_mm_subscription_payloads,
)
from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_sol_factory import (
    OfficialSolSdkBuilder,
    SolSdkBuilderProtocol,
)
from hypervector.live.hyperliquid_sol_parsing import validate_address
from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET

_EMERGENCY_CLOSE_SLIPPAGE_FRACTION = 0.01
_STREAM_CONFIRMATION_TIMEOUT_SECONDS = 5.0
_AUTHORITATIVE_RECONCILE_SECONDS = 60.0


def create_armed_apex_mm_adapter(
    config: ApexMMLiveConfig,
    *,
    environ: Mapping[str, str] | None = None,
    builder: SolSdkBuilderProtocol | None = None,
) -> ApexMMStreamingVenue:
    """Construct authenticated mainnet clients only after all live gates pass."""
    env = environ if environ is not None else os.environ
    address = (env.get(SECRET_ENV_WALLET) or "").strip()
    private_key = (env.get(SECRET_ENV_API_KEY) or "").strip()
    config.require_live_start(credentials_present=bool(address and private_key))
    validated = validate_address(address)
    sdk_builder = builder if builder is not None else OfficialSolSdkBuilder()
    info, exchange = sdk_builder.build(
        account_address=validated,
        private_key=private_key,
    )
    delegate = BtcHyperliquidAdapter(
        info=info,
        exchange=exchange,
        account_address=validated,
        max_notional_usd=config.max_inventory_notional_usd,
        slippage_fraction=_EMERGENCY_CLOSE_SLIPPAGE_FRACTION,
    )
    payloads = apex_mm_subscription_payloads(
        symbol=config.symbol,
        account_address=validated,
    )
    return ApexMMStreamingVenue(
        delegate=delegate,
        stream_factory=lambda mode: ApexMMVenueStream(
            feed=HyperliquidWebSocketFeed(
                symbol=config.symbol,
                subscription_payloads=payloads,
            ),
            symbol=config.symbol,
            account_mode=mode,
            depth_levels=config.depth_levels,
        ),
        maximum_book_age_ms=config.maximum_book_age_ms,
        confirmation_timeout_seconds=_STREAM_CONFIRMATION_TIMEOUT_SECONDS,
        authoritative_reconcile_seconds=_AUTHORITATIVE_RECONCILE_SECONDS,
    )
