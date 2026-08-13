"""Protocol adaptation tests for generic directional market execution."""

from __future__ import annotations

from unittest.mock import Mock

from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.multi_asset_directional_adapter import (
    MultiAssetDirectionalAdapter,
)


def test_generic_entry_routes_to_symbol_adapter_market_entry() -> None:
    """The shared engine uses IOC entry without changing legacy post-only calls."""
    delegate = Mock(spec=BtcHyperliquidAdapter)
    delegate.symbol = "ETH"
    delegate.submit_market_entry.return_value = "ack"
    adapter = MultiAssetDirectionalAdapter(delegate)

    result = adapter.submit_entry(
        side="long",
        requested_notional_usd=25.0,
        mark_price=2_500.0,
        client_order_id="0x0123456789abcdef0123456789abcdef",
    )

    assert result == "ack"
    delegate.submit_market_entry.assert_called_once_with(
        side="long",
        requested_notional_usd=25.0,
        mark_price=2_500.0,
        client_order_id="0x0123456789abcdef0123456789abcdef",
    )


def test_consistency_retry_invalidates_delegate_read_cache() -> None:
    """The generic adapter exposes fresh venue truth to bounded retries."""
    delegate = Mock(spec=BtcHyperliquidAdapter)
    delegate.symbol = "BTC"
    adapter = MultiAssetDirectionalAdapter(delegate)

    adapter.invalidate_reconciliation_cache()

    delegate.invalidate_reconciliation_cache.assert_called_once_with()
