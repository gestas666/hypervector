"""Causal validation and entry-age accounting for multi-asset polling."""

from __future__ import annotations

from hypervector.live.bidirectional_intents import StrategyIntent, WithheldIntent
from hypervector.live.multi_asset_market_bars import MultiAssetIntentPollerError
from hypervector.live.provider_evaluation import IntentBatch


def validate_intent_batch(
    batch: IntentBatch,
    strategy_id: str,
    symbol: str,
    prior: int,
    observed_ms: int,
) -> None:
    """Reject provider output outside its exact causal identity and boundary."""
    boundary = batch.latest_decision_time_ms
    if boundary < prior or boundary > observed_ms:
        raise MultiAssetIntentPollerError(
            f"invalid decision boundary for {strategy_id}/{symbol}: {boundary}"
        )
    for intent in batch.intents:
        if intent.strategy_id != strategy_id or intent.symbol != symbol:
            raise MultiAssetIntentPollerError(
                "provider emitted an intent with incorrect attribution"
            )
        if not prior < intent.decision_time_ms <= boundary:
            raise MultiAssetIntentPollerError(
                "provider intent lies outside its causal decision boundary"
            )
    for evaluation in batch.evaluations:
        if evaluation.strategy_id != strategy_id or evaluation.symbol != symbol:
            raise MultiAssetIntentPollerError(
                "provider emitted an evaluation with incorrect attribution"
            )
        if not prior < evaluation.decision_time_ms <= boundary:
            raise MultiAssetIntentPollerError(
                "provider evaluation lies outside its causal decision boundary"
            )


def record_fresh_intents(
    batch: IntentBatch,
    observed_ms: int,
    maximum_entry_delay_seconds: int,
    intents: list[StrategyIntent],
    source_withheld: list[WithheldIntent],
) -> None:
    """Route fresh entries and retain stale decisions as non-action evidence."""
    for intent in batch.intents:
        age = observed_ms - intent.decision_time_ms
        if age > maximum_entry_delay_seconds * 1_000:
            source_withheld.append(WithheldIntent(intent, "stale_completed_decision"))
        else:
            intents.append(intent)
