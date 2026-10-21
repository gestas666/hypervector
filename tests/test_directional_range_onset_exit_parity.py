"""Research-to-runtime exit parity for directional range-onset routes."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
    DirectionalRangeOnsetCollector,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

_BASE = pd.Timestamp("2026-08-07T14:00:00Z")
_DECISION_MS = int(_BASE.timestamp() * 1_000) + 60_000


def test_directional_range_maps_blocked_opposite_cross_to_owned_exit() -> None:
    """A raw researched exit must survive an opposed entry-context filter."""
    raw_exit = replace(
        _evaluation("short"),
        decision_action="long_exit",
        eligible=False,
        reason="entry_context_dual_mtf_opposed",
        side=None,
        exit_sides=frozenset({"long"}),
        exit_reason="range_onset_signal",
    )

    result = _collect(raw_exit)

    assert result.intents == ()
    assert result.evaluations[0].decision_action == "close_long"
    assert result.evaluations[0].exit_sides == frozenset({"long"})
    assert result.evaluations[0].exit_reason == "opposite_range_onset"


def test_directional_range_drops_exit_for_disabled_position_side() -> None:
    """An ETH-long provider must not claim exit authority over short positions."""
    desired_entry = replace(
        _evaluation("long"),
        exit_sides=frozenset({"short"}),
        exit_reason="range_onset_signal",
    )

    result = _collect(desired_entry)

    assert [(row.symbol, row.side) for row in result.intents] == [("ETH", "long")]
    assert result.evaluations[0].exit_sides == frozenset()
    assert result.evaluations[0].exit_reason is None


def _collect(evaluation: ProviderEvaluation) -> IntentBatch:
    collector = DirectionalRangeOnsetCollector(
        strategy_id=ETH_RANGE_LONG_STRATEGY,
        source_collector=lambda *args, **kwargs: IntentBatch(
            (), evaluation.decision_time_ms, (evaluation,)
        ),
    )
    return collector(
        pd.DataFrame(),
        symbol="ETH",
        observed_at=_BASE,
        after_decision_time_ms=0,
    )


def _evaluation(side: str) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id="source",
        symbol="ETH",
        decision_time_ms=_DECISION_MS,
        reference_price=100.0,
        decision_action=f"enter_{side}",
        eligible=True,
        reason="entry_signal_present",
        side=side,
        readiness=SignalReadiness(
            side=side,
            conditions_met=2,
            conditions_required=2,
            blockers=(),
            indicators=("SOURCE READY",),
        ),
        trigger="source_entry",
    )
