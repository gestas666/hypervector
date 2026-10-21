"""Preserve unconditional owned-position deadlines during strategy-data failure."""

from __future__ import annotations

from datetime import datetime
import math
from typing import TYPE_CHECKING

from hypervector.live.bidirectional_intents import IntentRoutingReport
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
    aware,
    reconcile_engines,
)
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError

if TYPE_CHECKING:
    from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
    from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner


def poll_with_deadlines(
    runner: MultiAssetLiveRunner,
    observed: datetime,
    funding_start_ms: int,
) -> CohortIntentPoll:
    """Preserve acquisition errors after independently required deadline handling."""
    try:
        return runner._intent_poller.poll(observed)
    except TransientCohortMarketDataError:
        _finish_unconditional_deadlines(runner, funding_start_ms)
        raise


def _finish_unconditional_deadlines(
    runner: MultiAssetLiveRunner, funding_start_ms: int
) -> None:
    funding_end_ms = int(aware(runner._now_fn()).timestamp() * 1_000)
    venues = reconcile_engines(
        runner._symbols, runner._engines, funding_start_ms, funding_end_ms
    )
    observed_ms = int(aware(runner._now_fn()).timestamp() * 1_000)
    prices = reconciled_position_prices(runner._symbols, venues)
    _, actions = runner._maximum_hold_controller.actions(
        observed_ms, prices, runner._latest_evaluations, unconditional_only=True
    )
    if not actions:
        return
    report = IntentRoutingReport(actions, ())
    with runner.execution_phase():
        runner._finish_cycle(
            poll=CohortIntentPoll((), prices),
            operator_actions=(),
            routed=report,
            routed_actions=actions,
            venues=venues,
            funding_start_ms=funding_start_ms,
            funding_end_ms=funding_end_ms,
            observed_ms=observed_ms,
            heartbeat=False,
        )


def reconciled_position_prices(
    symbols: tuple[str, ...], venues: tuple[HyperliquidReconciliationSnapshot, ...]
) -> dict[str, float]:
    """Derive explicit account marks only from valid nonzero native position facts."""
    prices: dict[str, float] = {}
    for symbol, venue in zip(symbols, venues, strict=True):
        position = venue.position
        size, notional = position.size_signed, position.position_value_usd
        if not math.isfinite(size):
            raise MultiAssetLiveRunnerError(
                f"{symbol} reconciled position size is not finite"
            )
        if size == 0.0:
            continue
        if not math.isfinite(notional) or notional <= 0:
            raise MultiAssetLiveRunnerError(
                f"{symbol} reconciled position notional must be positive and finite"
            )
        price = notional / abs(size)
        if not math.isfinite(price) or price <= 0:
            raise MultiAssetLiveRunnerError(
                f"{symbol} reconciled position price must be positive and finite"
            )
        prices[symbol] = price
    return prices
