"""Versioned HYPE compression provider requiring breakout-side agreement."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.breakout_feature_filter_provider import (
    CanonicalBreakoutCollectorProtocol,
)
from hypervector.live.hype_breakout_compression_provider import (
    HypeCompressionBreakoutCollector,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation

HYPE_COMPRESSION_ALIGNMENT_STRATEGY = (
    "hype_breakout_compression_alignment_bidirectional_v2"
)
_BOTH_SIDES = frozenset({"long", "short"})


class HypeCompressionAlignmentCollector:
    """Admit frozen compression onsets only when both causal sides agree."""

    def __init__(
        self,
        *,
        canonical_collector: CanonicalBreakoutCollectorProtocol | None = None,
        execution_enabled: bool = False,
        execution_sides: frozenset[str] = _BOTH_SIDES,
    ) -> None:
        """Bind the v1 compression source under the versioned repair identity."""
        if not execution_sides or not execution_sides.issubset(_BOTH_SIDES):
            raise ValueError("HYPE alignment execution sides must be long or short")
        self._compression = HypeCompressionBreakoutCollector(
            canonical_collector=canonical_collector,
            execution_enabled=execution_enabled,
        )
        self._execution_sides = execution_sides

    @property
    def execution_sides(self) -> frozenset[str]:
        """Return sides allowed to open while the opposite retains exit authority."""
        return self._execution_sides

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return only fresh compression onsets with measured side agreement."""
        source = self._compression(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        evaluations = tuple(
            _evaluation(row, self._execution_sides) for row in source.evaluations
        )
        intents = tuple(_intent(row) for row in evaluations if row.eligible)
        return IntentBatch(intents, source.latest_decision_time_ms, evaluations)


def _evaluation(
    source: ProviderEvaluation,
    execution_sides: frozenset[str],
) -> ProviderEvaluation:
    relation = source.readiness.metrics.get("breakout_side_relation")
    aligned = relation == "aligned"
    signal_eligible = source.eligible and aligned
    exit_sides = _opposite_exit_sides(source.side, signal_eligible, execution_sides)
    eligible = signal_eligible and source.side in execution_sides
    reason = source.reason if not source.eligible else _alignment_reason(relation)
    if exit_sides:
        reason = "opposite_hype_alignment"
    blockers = source.readiness.blockers
    if source.eligible and not aligned:
        blockers = (*blockers, reason)
    readiness = replace(
        source.readiness,
        conditions_met=source.readiness.conditions_met + int(aligned),
        conditions_required=source.readiness.conditions_required + 1,
        blockers=tuple(dict.fromkeys(blockers)),
        indicators=(
            *source.readiness.indicators,
            f"SIDE ALIGNMENT {str(relation).upper()}",
        ),
        metrics={
            **source.readiness.metrics,
            "alignment_only": True,
            "breakout_side_alignment_required": True,
        },
    )
    return replace(
        source,
        strategy_id=HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
        decision_action=_decision_action(source.side, eligible, exit_sides),
        eligible=eligible,
        reason=reason,
        readiness=readiness,
        trigger=_trigger(eligible, exit_sides),
        exit_sides=exit_sides,
        exit_reason="opposite_hype_alignment" if exit_sides else None,
    )


def _opposite_exit_sides(
    signal_side: str | None,
    signal_eligible: bool,
    execution_sides: frozenset[str],
) -> frozenset[str]:
    if not signal_eligible or signal_side not in _BOTH_SIDES:
        return frozenset()
    opposite = "short" if signal_side == "long" else "long"
    return frozenset({opposite}) if opposite in execution_sides else frozenset()


def _decision_action(
    side: str | None,
    eligible: bool,
    exit_sides: frozenset[str],
) -> str:
    if eligible:
        return f"enter_{side}"
    return f"close_{next(iter(exit_sides))}" if exit_sides else "hold"


def _trigger(eligible: bool, exit_sides: frozenset[str]) -> str:
    if eligible:
        return "hype_compression_alignment"
    return "opposite_hype_alignment_exit" if exit_sides else "none"


def _alignment_reason(value: object) -> str:
    if value == "aligned":
        return "hype_compression_alignment_ready"
    if value == "opposed":
        return "breakout_side_opposed"
    return "breakout_side_unavailable"


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    side = evaluation.side
    if side not in {"long", "short"}:
        raise RuntimeError("eligible HYPE alignment evaluation lacks a side")
    return StrategyIntent(
        strategy_id=HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
        symbol=evaluation.symbol,
        side=side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"hype_compression_alignment:{side}",
    )
