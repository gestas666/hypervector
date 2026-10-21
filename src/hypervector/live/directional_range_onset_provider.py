"""Directional ETH/SOL range-onset providers with opposite-onset exits."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.multi_asset_signal_source import (
    collect_range_onset_bidirectional_intents,
)

ETH_RANGE_LONG_STRATEGY = "eth_range_onset_long_dual_mtf_v2"
SOL_RANGE_SHORT_STRATEGY = "sol_range_onset_short_dual_mtf_v2"
_SPECS = {
    ETH_RANGE_LONG_STRATEGY: ("ETH", "long"),
    SOL_RANGE_SHORT_STRATEGY: ("SOL", "short"),
}


class RangeSourceCollectorProtocol(Protocol):
    """Callable contract for a completed-bar range-onset source."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch: ...


class DirectionalRangeOnsetCollector:
    """Trade the evidence-supported range side and close on opposite onset."""

    def __init__(
        self,
        *,
        strategy_id: str,
        source_collector: RangeSourceCollectorProtocol | None = None,
    ) -> None:
        """Bind one exact ETH-long or SOL-short directional contract."""
        if strategy_id not in _SPECS:
            raise ValueError("unsupported directional range-onset strategy")
        self._strategy_id = strategy_id
        self._symbol, self._side = _SPECS[strategy_id]
        self._source = source_collector or partial(
            collect_range_onset_bidirectional_intents,
            entry_context_policies={self._symbol: "dual_mtf_not_opposed"},
        )

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return desired-side entries and opposite-onset exit authority."""
        if symbol != self._symbol:
            raise ValueError(f"{self._strategy_id} supports {self._symbol} only")
        source = self._source(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        evaluations = tuple(
            _directional_evaluation(row, self._strategy_id, self._side)
            for row in source.evaluations
        )
        intents = tuple(_intent(row) for row in evaluations if row.eligible)
        return IntentBatch(intents, source.latest_decision_time_ms, evaluations)


def _directional_evaluation(
    source: ProviderEvaluation,
    strategy_id: str,
    desired_side: str,
) -> ProviderEvaluation:
    opposite = "short" if desired_side == "long" else "long"
    if desired_side in source.exit_sides:
        return replace(
            source,
            strategy_id=strategy_id,
            decision_action=f"close_{desired_side}",
            eligible=False,
            reason="opposite_range_onset_exit",
            exit_sides=frozenset({desired_side}),
            exit_reason="opposite_range_onset",
            trigger="opposite_range_onset_exit",
        )
    if source.eligible and source.side == opposite:
        return replace(
            source,
            strategy_id=strategy_id,
            decision_action=f"close_{desired_side}",
            eligible=False,
            reason="opposite_range_onset_exit",
            exit_sides=frozenset({desired_side}),
            exit_reason="opposite_range_onset",
            trigger="opposite_range_onset_exit",
        )
    if source.eligible and source.side != desired_side:
        raise ValueError("eligible range source is missing a supported side")
    return replace(
        source,
        strategy_id=strategy_id,
        decision_action=(
            f"enter_{desired_side}" if source.eligible else source.decision_action
        ),
        reason=("directional_range_entry" if source.eligible else source.reason),
        trigger="directional_range_onset" if source.eligible else source.trigger,
        exit_sides=frozenset(),
        exit_reason=None,
    )


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    if evaluation.side not in {"long", "short"}:
        raise ValueError("eligible directional range evaluation requires a side")
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol=evaluation.symbol,
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"{evaluation.trigger}:{evaluation.side}",
    )
