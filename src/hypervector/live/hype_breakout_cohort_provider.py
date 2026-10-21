"""Cross-asset HT-Breakout signal provider with legacy journal identity."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hype_breakout_entry_telemetry import (
    build_hype_entry_feature_telemetry,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness
from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.live.sol_range_onset_decision_source import (
    build_completed_live_decisions,
)

HYPE_BREAKOUT_COHORT_STRATEGY = "hype_breakout_onset_bidirectional_v1"
_MINUTE_MS = 60_000
_ENTRY_FEATURE_HISTORY_MINUTES = 60
_SUPPORTED_SYMBOLS = frozenset({"BTC", "ETH", "SOL", "HYPE"})


class HypeDecisionBuilderProtocol(Protocol):
    """Injectable completed-bar regime decision builder."""

    def __call__(
        self,
        raw_bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[SolLiveDecision, ...]: ...


class HypeBreakoutOnsetCollector:
    """Expose fresh 5m breakout transitions with exact symbol attribution."""

    def __init__(
        self,
        *,
        decision_builder: HypeDecisionBuilderProtocol = build_completed_live_decisions,
    ) -> None:
        """Store the causal decision source and startup seed boundary."""
        self._decision_builder = decision_builder
        self._highest_requested_boundary: dict[str, int] = {}

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return unseen setup states and only fresh directional onset intents."""
        if symbol not in _SUPPORTED_SYMBOLS:
            raise ValueError("breakout-onset provider supports BTC/ETH/SOL/HYPE only")
        boundary = _boundary(after_decision_time_ms)
        seed_query = self._is_seed_query(symbol, boundary)
        decisions = self._decision_builder(
            bars,
            observed_at=observed_at,
            after_decision_time_ms=max(
                0,
                boundary - _ENTRY_FEATURE_HISTORY_MINUTES * _MINUTE_MS - 1,
            ),
        )
        evaluations = _evaluations_after(decisions, boundary, symbol)
        intents = () if seed_query else _eligible_intents(evaluations)
        latest = evaluations[-1].decision_time_ms if evaluations else boundary
        return IntentBatch(intents, latest, evaluations)

    def _is_seed_query(self, symbol: str, boundary: int) -> bool:
        prior = self._highest_requested_boundary.get(symbol)
        seed_query = prior is not None and boundary < prior
        self._highest_requested_boundary[symbol] = max(boundary, prior or 0)
        return seed_query


def _evaluations_after(
    decisions: tuple[SolLiveDecision, ...],
    boundary: int,
    symbol: str,
) -> tuple[ProviderEvaluation, ...]:
    prior_state: str | None = None
    evaluations: list[ProviderEvaluation] = []
    for position, decision in enumerate(decisions):
        if decision.decision_time_ms <= boundary:
            prior_state = decision.state_5m
            continue
        side = _structural_side(decision.structural_direction)
        entry_features = build_hype_entry_feature_telemetry(
            decisions,
            position,
            side,
        )
        evaluations.append(_evaluation(decision, prior_state, symbol, entry_features))
        prior_state = decision.state_5m
    return tuple(evaluations)


def _evaluation(
    decision: SolLiveDecision,
    prior_state: str | None,
    symbol: str,
    entry_features: dict[str, ReadinessMetric],
) -> ProviderEvaluation:
    state_breakout = decision.state_5m == "BREAKOUT"
    onset = state_breakout and prior_state not in {None, "BREAKOUT"}
    side = _structural_side(decision.structural_direction)
    eligible = onset and side is not None
    return ProviderEvaluation(
        strategy_id=HYPE_BREAKOUT_COHORT_STRATEGY,
        symbol=symbol,
        decision_time_ms=decision.decision_time_ms,
        reference_price=decision.reference_price,
        decision_action=f"enter_{side}" if eligible else "hold",
        eligible=eligible,
        reason=_reason(state_breakout, onset, side),
        side=side,
        readiness=_readiness(
            decision,
            prior_state,
            state_breakout,
            onset,
            side,
            entry_features,
        ),
        trigger="5m_breakout_onset" if onset else "none",
        primary_regime=decision.primary_regime,
        state_1m=decision.state_1m,
        state_5m=decision.state_5m,
        context_15m=decision.context_15m,
        confidence=decision.confidence,
    )


def _readiness(
    decision: SolLiveDecision,
    prior_state: str | None,
    state_breakout: bool,
    onset: bool,
    side: str | None,
    entry_features: dict[str, ReadinessMetric],
) -> SignalReadiness:
    directional = side is not None
    return SignalReadiness(
        side=side,
        conditions_met=sum((state_breakout, onset, directional)),
        conditions_required=3,
        blockers=_blockers(state_breakout, onset, side),
        indicators=(
            f"5M {decision.state_5m}",
            f"ONSET {'YES' if onset else 'NO'}",
            f"STRUCT {decision.structural_direction.upper()}",
            _breakout_side_indicator(side, decision.breakout_side),
            f"CONF {decision.confidence * 100.0:.0f}% TELEMETRY",
            _entry_feature_indicator(entry_features),
        ),
        metrics={
            "breakout_onset": onset,
            "confidence": decision.confidence,
            "prior_state_5m": prior_state,
            "state_5m": decision.state_5m,
            "structural_direction": decision.structural_direction,
            "breakout_side": decision.breakout_side,
            "breakout_side_relation": _breakout_side_relation(
                side,
                decision.breakout_side,
            ),
            **entry_features,
        },
    )


def _breakout_side_relation(side: str | None, breakout_side: str | None) -> str:
    if side is None or breakout_side is None:
        return "unavailable"
    return "aligned" if side == breakout_side else "opposed"


def _breakout_side_indicator(side: str | None, breakout_side: str | None) -> str:
    breakout = (breakout_side or "N/A").upper()
    structural = (side or "N/A").upper()
    return f"5M BREAKOUT {breakout} / SMA {structural} [REPORT ONLY]"


def _entry_feature_indicator(values: dict[str, ReadinessMetric]) -> str:
    status = values["entry_feature_status"]
    return f"ENTRY ATTRIBUTION {status} [REPORT ONLY]".upper()


def _blockers(
    state_breakout: bool,
    onset: bool,
    side: str | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not state_breakout:
        blockers.append("5m_not_breakout")
    elif not onset:
        blockers.append("awaiting_new_5m_breakout_onset")
    if side is None:
        blockers.append("structural_direction_neutral")
    return tuple(blockers)


def _reason(state_breakout: bool, onset: bool, side: str | None) -> str:
    if not state_breakout:
        return "5m_not_breakout"
    if not onset:
        return "awaiting_new_5m_breakout_onset"
    if side is None:
        return "structural_direction_neutral"
    return "breakout_onset_directional"


def _eligible_intents(
    evaluations: tuple[ProviderEvaluation, ...],
) -> tuple[StrategyIntent, ...]:
    return tuple(_intent(value) for value in evaluations if value.eligible)


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    if evaluation.side not in {"long", "short"}:
        raise ValueError("eligible HT-Breakout onset is missing a side")
    return StrategyIntent(
        strategy_id=HYPE_BREAKOUT_COHORT_STRATEGY,
        symbol=evaluation.symbol,
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"{evaluation.symbol.lower()}_5m_breakout_onset:{evaluation.side}",
    )


def _structural_side(value: str) -> str | None:
    return value if value in {"long", "short"} else None


def _boundary(value: int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("after_decision_time_ms must be a nonnegative integer")
    return value
