"""Signal capabilities for the screened hourly price mechanisms."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.hourly_price_provider import HOURLY_PRICE_SYMBOLS
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_route_contract_validation import (
    binds_signal_anchors,
)

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import StrategyProviderConfig


def validate_hourly_price_provider(provider: StrategyProviderConfig) -> None:
    """Reject a mislabeled clock, an uncomputed symbol, or a dropped side."""
    valid = (
        set(provider.symbols).issubset(HOURLY_PRICE_SYMBOLS)
        and provider.timeframe == "15m"
        and provider.sides == frozenset({"long", "short"})
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=True)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "hourly price research requires qualified symbols, both emitted sides, "
            "the 15m source, opposite-entry close, and no absolute target"
        )
