"""Stable configuration and intent payloads for cohort telemetry."""

from __future__ import annotations

from hypervector.live.bidirectional_intents import (
    RoutingAction,
    StrategyIntent,
    WithheldIntent,
)
from hypervector.live.cohort_profit_lock_override import grouped_profit_lock_payload
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    StrategyProviderConfig,
)


def routing_action_payload(action: RoutingAction) -> dict[str, object]:
    """Serialize an action with the timestamp and boundary actually checked."""
    return {
        "action": action.action,
        "strategy_id": action.strategy_id,
        "symbol": action.symbol,
        "side": action.side,
        "decision_time_ms": action.decision_time_ms,
        "reference_price": action.reference_price,
        "regime_alignment_score": action.regime_alignment_score,
        "regime_alignment_stance": action.regime_alignment_stance,
        "regime_decision_time_ms": action.regime_decision_time_ms,
        "regime_alignment_basis": action.regime_alignment_basis,
        "exit_reason": action.exit_reason,
        "submission_observed_at_ms": action.submission_observed_at_ms,
        "submission_age_ms": action.submission_age_ms,
        "submission_limit_ms": action.submission_limit_ms,
        "submission_boundary": action.submission_boundary,
    }


def withheld_intent_payload(item: WithheldIntent) -> dict[str, object]:
    """Serialize a non-action without pretending its clock observed dispatch."""
    return {
        **intent_payload(item.intent),
        "reason": item.reason,
        "submission_observed_at_ms": item.submission_observed_at_ms,
        "submission_age_ms": item.submission_age_ms,
        "submission_limit_ms": item.submission_limit_ms,
        "submission_boundary": item.submission_boundary,
    }


def asset_config_payload(asset: AssetLiveConfig) -> dict[str, object]:
    """Project one effective asset configuration without secrets."""
    return {
        "symbol": asset.symbol,
        "sides": ["long", "short"],
        "leverage": asset.leverage,
        "venue_max_leverage": asset.venue_max_leverage,
        "margin_fraction": asset.margin_fraction,
        "max_notional_usd": asset.max_notional_usd,
        "entry_slippage_cap_fraction": (asset.effective_entry_slippage_cap_fraction),
        "market_slippage_cap_fraction": asset.market_slippage_cap_fraction,
        "stop_bps": asset.stop_bps,
        "maximum_hold_seconds": asset.maximum_hold_seconds,
    }


def provider_config_payload(provider: StrategyProviderConfig) -> dict[str, object]:
    """Project one provider configuration with exact directional authority."""
    directional: dict[str, dict[str, dict[str, float]]] = {}
    for symbol, side, sizing in provider.directional_sizing_overrides:
        directional.setdefault(symbol, {})[side] = sizing.as_payload()
    return {
        "strategy_id": provider.strategy_id,
        "symbols": list(provider.symbols),
        "sides": sorted(provider.sides),
        "priority": provider.priority,
        "position_policy": provider.position_policy,
        "timeframe": provider.timeframe,
        "maximum_entry_delay_seconds": provider.maximum_entry_delay_seconds,
        "execution_symbols": list(provider.execution_symbols),
        "execution_side_overrides": {
            symbol: sorted(sides) for symbol, sides in provider.execution_side_overrides
        },
        "stop_bps_overrides": dict(provider.stop_bps_overrides),
        "sizing_overrides": {
            symbol: sizing.as_payload() for symbol, sizing in provider.sizing_overrides
        },
        "directional_sizing_overrides": directional,
        "profit_lock_overrides": grouped_profit_lock_payload(
            provider.profit_lock_overrides
        ),
        "execution": provider.execution.as_payload(),
    }


def intent_payload(intent: StrategyIntent) -> dict[str, object]:
    """Project one attributed provider intent."""
    return {
        "strategy_id": intent.strategy_id,
        "symbol": intent.symbol,
        "side": intent.side,
        "decision_time_ms": intent.decision_time_ms,
        "reference_price": intent.reference_price,
        "source_reason": intent.reason,
        "stop_anchor": intent.stop_anchor,
        "target_anchor": intent.target_anchor,
        "regime_alignment_score": intent.regime_alignment_score,
        "regime_alignment_stance": intent.regime_alignment_stance,
        "regime_decision_time_ms": intent.regime_decision_time_ms,
        "regime_alignment_basis": intent.regime_alignment_basis,
    }
