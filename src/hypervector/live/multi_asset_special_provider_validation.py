"""Signal capabilities for specialized multi-asset strategy providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_route_contract_validation import (
    binds_signal_anchors,
)

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import StrategyProviderConfig

_BOTH_SIDES = frozenset({"long", "short"})


def validate_research_pending_market_observer(
    provider: StrategyProviderConfig,
) -> None:
    """Keep data-only roster coverage structurally execution-disabled."""
    valid = (
        bool(provider.symbols)
        and provider.timeframe == "15m"
        and provider.execution_symbols == ()
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "research-pending market observer must be 15m and execution-disabled"
        )


def validate_spcx_cash_open(provider: StrategyProviderConfig) -> None:
    """Require the SPCX cash-open signal scope and its absolute target anchor."""
    valid = (
        provider.symbols == ("xyz:SPCX",)
        and provider.sides == _BOTH_SIDES
        and provider.timeframe == "15m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(
            provider.execution, stop_anchor=False, target_anchor=True
        )
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "SPCX cash-open requires xyz:SPCX, both emitted sides, the 15m signal, "
            "opposite-entry close, a fixed stop, and its absolute target anchor"
        )


def validate_hype_native_breakout(provider: StrategyProviderConfig) -> None:
    """Require the HYPE native-breakout signal scope."""
    valid = (
        provider.symbols == ("HYPE",)
        and provider.timeframe == "1m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "native breakout-onset requires HYPE-only 1m scope, opposite-entry "
            "close, a fixed stop, and no absolute target"
        )


def validate_hype_compression_alignment(provider: StrategyProviderConfig) -> None:
    """Require the HYPE alignment signal scope."""
    valid = (
        provider.symbols == ("HYPE",)
        and provider.timeframe == "1m"
        and provider.position_policy == "enter_and_close"
        and binds_signal_anchors(provider.execution, stop_anchor=False)
    )
    if not valid:
        raise MultiAssetLiveConfigError(
            "HYPE compression alignment breakout requires HYPE-only 1m scope, "
            "opposite-entry close, a fixed stop, and no absolute target"
        )
