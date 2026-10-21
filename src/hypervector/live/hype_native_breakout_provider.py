"""HYPE-only identity wrapper around the canonical breakout-onset signal."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

import pandas as pd

from hypervector.live.hype_breakout_cohort_provider import (
    HYPE_BREAKOUT_COHORT_STRATEGY,
    HypeBreakoutOnsetCollector,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation

HYPE_NATIVE_BREAKOUT_STRATEGY = "hype_native_breakout_onset_bidirectional_v2"
HYPE_NATIVE_BREAKOUT_LONG_STRATEGY = "hype_native_breakout_onset_long_v3"
_HYPE_SYMBOL = "HYPE"
_SIDES = frozenset({"long", "short"})


class CanonicalHypeCollectorProtocol(Protocol):
    """Canonical breakout collector adapted under a clean experiment identity."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return the canonical HYPE breakout batch."""
        ...


class HypeNativeBreakoutOnsetCollector:
    """Preserve canonical HYPE signals under a HYPE-only evidence identity."""

    def __init__(
        self,
        *,
        canonical_collector: CanonicalHypeCollectorProtocol | None = None,
        strategy_id: str = HYPE_NATIVE_BREAKOUT_STRATEGY,
        entry_sides: frozenset[str] = _SIDES,
    ) -> None:
        """Bind the unchanged canonical signal implementation."""
        if strategy_id not in {
            HYPE_NATIVE_BREAKOUT_STRATEGY,
            HYPE_NATIVE_BREAKOUT_LONG_STRATEGY,
        }:
            raise ValueError("unsupported HYPE-native strategy identity")
        if not entry_sides or not entry_sides <= _SIDES:
            raise ValueError("HYPE-native entry sides must contain long and/or short")
        self._canonical = canonical_collector or HypeBreakoutOnsetCollector()
        self._strategy_id = strategy_id
        self._entry_sides = entry_sides

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return canonical signals while rejecting every non-HYPE market."""
        if symbol != _HYPE_SYMBOL:
            raise ValueError("native breakout-onset provider is HYPE-only")
        canonical = self._canonical(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        _require_canonical_batch(canonical)
        return IntentBatch(
            intents=tuple(
                replace(row, strategy_id=self._strategy_id)
                for row in canonical.intents
                if row.side in self._entry_sides
            ),
            latest_decision_time_ms=canonical.latest_decision_time_ms,
            evaluations=tuple(
                _adapt_evaluation(row, self._strategy_id, self._entry_sides)
                for row in canonical.evaluations
            ),
        )


def _require_canonical_batch(batch: IntentBatch) -> None:
    rows = batch.intents + batch.evaluations
    if any(row.strategy_id != HYPE_BREAKOUT_COHORT_STRATEGY for row in rows):
        raise ValueError("native provider requires canonical HYPE breakout identity")
    if any(row.symbol != _HYPE_SYMBOL for row in rows):
        raise ValueError("native provider requires canonical HYPE symbol attribution")


def _adapt_evaluation(
    row: ProviderEvaluation,
    strategy_id: str,
    entry_sides: frozenset[str],
) -> ProviderEvaluation:
    if not row.eligible or row.side in entry_sides:
        return replace(row, strategy_id=strategy_id)
    open_side = "short" if row.side == "long" else "long"
    return replace(
        row,
        strategy_id=strategy_id,
        eligible=False,
        decision_action=f"close_{open_side}",
        reason="opposite_native_onset_exit_only",
        exit_sides=frozenset({open_side}),
        exit_reason="opposite_native_onset",
    )
