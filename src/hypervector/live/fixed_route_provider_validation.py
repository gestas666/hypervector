"""Signal capabilities for the directional range, ZEC and SPCX routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_route_contract_validation import (
    binds_signal_anchors,
)

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import StrategyProviderConfig


def validate_directional_range(provider: StrategyProviderConfig) -> None:
    """Require the directional range symbol and the one side it enters."""
    symbol, side = (
        ("ETH", "long")
        if provider.strategy_id == ETH_RANGE_LONG_STRATEGY
        else ("SOL", "short")
    )
    valid = (
        provider.symbols == (symbol,)
        and side in provider.sides
        and provider.timeframe == "1m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            f"directional range route {provider.strategy_id} requires {symbol}-only "
            f"1m scope, its emitted {side} side, opposite-entry close, a fixed stop, "
            "and no absolute target"
        )


def validate_zec_donchian_long(provider: StrategyProviderConfig) -> None:
    """Require ZEC observation and the long side the channel signal emits."""
    valid = (
        provider.symbols == ("ZEC",)
        and "long" in provider.sides
        and provider.timeframe == "15m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=True)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "ZEC Donchian requires ZEC-only 15m scope, its emitted long side, "
            "opposite-entry close, and no absolute target"
        )


def validate_spcx_cash_session_long(provider: StrategyProviderConfig) -> None:
    """Require SPCX observation and the long side the session signal emits."""
    valid = (
        provider.symbols == ("xyz:SPCX",)
        and "long" in provider.sides
        and provider.timeframe == "15m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "SPCX cash-session requires xyz:SPCX-only 15m scope, its emitted long "
            "side, opposite-entry close, a fixed stop, and no absolute target"
        )
