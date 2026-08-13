"""Causal HYPE-only compression-plus-breakout provider."""

from __future__ import annotations

from hypervector.live.breakout_feature_filter_provider import (
    BreakoutFeatureFilterCollector,
    BreakoutFeatureFilterContract,
    CanonicalBreakoutCollectorProtocol,
)

HYPE_COMPRESSION_BREAKOUT_STRATEGY = (
    "hype_breakout_compression_pullback_bidirectional_v1"
)
_HYPE_CONTRACT = BreakoutFeatureFilterContract(
    strategy_id=HYPE_COMPRESSION_BREAKOUT_STRATEGY,
    symbol="HYPE",
    trigger="hype_compression_breakout_pullback",
    ready_reason="hype_compression_breakout_ready",
    intent_reason="hype_compression_breakout_pullback",
    maximum_prior_bbwp_min_15m=40.0,
    maximum_directional_body_bps=0.0,
    maximum_5m_bbwp_percentile=50.0,
    stop_bps=80.0,
    maximum_hold_seconds=28_800,
    hard_maximum_hold_seconds=86_400,
)


class HypeCompressionBreakoutCollector(BreakoutFeatureFilterCollector):
    """Admit HYPE onsets matching the frozen 50/40 pullback contract."""

    def __init__(
        self,
        *,
        canonical_collector: CanonicalBreakoutCollectorProtocol | None = None,
        execution_enabled: bool = False,
    ) -> None:
        """Bind the HYPE filter and its explicit runtime authority label."""
        super().__init__(
            _HYPE_CONTRACT,
            canonical_collector=canonical_collector,
            execution_enabled=execution_enabled,
        )
