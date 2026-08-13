"""Causal ETH-only breakout transfer provider."""

from __future__ import annotations

from hypervector.live.breakout_feature_filter_provider import (
    BreakoutFeatureFilterCollector,
    BreakoutFeatureFilterContract,
    CanonicalBreakoutCollectorProtocol,
)

ETH_BREAKOUT_TRANSFER_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_ETH_CONTRACT = BreakoutFeatureFilterContract(
    strategy_id=ETH_BREAKOUT_TRANSFER_STRATEGY,
    symbol="ETH",
    trigger="eth_breakout_precompression_pullback",
    ready_reason="eth_breakout_transfer_ready",
    intent_reason="eth_breakout_precompression_pullback",
    maximum_prior_bbwp_min_15m=40.0,
    maximum_directional_body_bps=0.0,
    stop_bps=60.0,
    maximum_hold_seconds=43_200,
)


class EthBreakoutTransferCollector(BreakoutFeatureFilterCollector):
    """Admit fresh ETH onsets after compression and a directional pullback."""

    def __init__(
        self,
        *,
        canonical_collector: CanonicalBreakoutCollectorProtocol | None = None,
        execution_enabled: bool = False,
    ) -> None:
        """Bind the frozen ETH contract and explicit runtime authority label."""
        super().__init__(
            _ETH_CONTRACT,
            canonical_collector=canonical_collector,
            execution_enabled=execution_enabled,
        )
