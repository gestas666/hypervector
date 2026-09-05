"""Convert existing causal signal engines into attributed cohort intents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import math
import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hulk_smash_live_decisions import (
    HulkDecisionConfigProtocol,
    HulkSmashLiveDecision,
    build_completed_hulk_decisions,
)
from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.live.sol_range_onset_decision_source import (
    build_completed_live_decisions,
)
from hypervector.research.market_cipher_strategy_research import (
    resolve_hulk_research_profile,
)
from hypervector.live.provider_readiness import SignalReadiness

_HULK_STRATEGY = "hulk_expansion_bidirectional_tuned_v2"
_RANGE_STRATEGY = "range_onset_bidirectional_v1"


class HulkDecisionBuilderProtocol(Protocol):
    """Injectable completed-bar Hulk builder used by tests and runtime."""

    def __call__(
        self,
        raw_bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        config: HulkDecisionConfigProtocol,
        after_decision_time_ms: int | None,
        allowed_sides: frozenset[str],
    ) -> tuple[HulkSmashLiveDecision, ...]: ...


class RangeDecisionBuilderProtocol(Protocol):
    """Injectable completed-bar range-onset builder."""

    def __call__(
        self,
        raw_bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[SolLiveDecision, ...]: ...


@dataclass(frozen=True)
class HulkBidirectionalSourceConfig:
    """Frozen bidirectional Hulk parameters from the journaled profile."""

    backtest_lab_root: Path
    supertrend_period: int
    supertrend_multiplier: float
    adx_period: int
    squeeze_period: int
    minimum_score: int
    pivot_bars: int
    adx_usable: float
    adx_trending: float


@dataclass(frozen=True)
class IntentBatch:
    """All entry intents plus the latest processed decision boundary."""

    intents: tuple[StrategyIntent, ...]
    latest_decision_time_ms: int
    evaluations: tuple[ProviderEvaluation, ...] = ()


@dataclass(frozen=True)
class ProviderEvaluation:
    """One backend-authored completed-bar setup and firing-readiness record."""

    strategy_id: str
    symbol: str
    decision_time_ms: int
    reference_price: float
    decision_action: str
    eligible: bool
    reason: str
    side: str | None
    readiness: SignalReadiness
    score: int | None = None
    minimum_score: int | None = None
    trigger: str | None = None
    primary_regime: str | None = None
    state_1m: str | None = None
    state_5m: str | None = None
    context_15m: str | None = None
    confidence: float | None = None
    exit_sides: frozenset[str] = frozenset()
    exit_reason: str | None = None
    backend_non_action_reason: str | None = None
    target_anchor: float | None = None

    def __post_init__(self) -> None:
        """Reject malformed provider identity, direction, and market evidence."""
        if not self.strategy_id.strip() or not self.symbol.strip():
            raise ValueError("provider evaluation identity must be non-empty")
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
        ):
            raise ValueError("decision_time_ms must be a nonnegative integer")
        if not math.isfinite(self.reference_price) or self.reference_price <= 0.0:
            raise ValueError("reference_price must be positive and finite")
        if not isinstance(self.eligible, bool):
            raise ValueError("eligible must be boolean")
        if not self.decision_action.strip() or not self.reason.strip():
            raise ValueError("provider action and reason must be non-empty")
        if self.side not in {None, "long", "short"}:
            raise ValueError("provider side must be long, short, or None")
        if self.eligible and self.side is None:
            raise ValueError("eligible provider evaluations require a side")
        if not self.exit_sides.issubset({"long", "short"}):
            raise ValueError("provider exit sides must contain only long and/or short")
        if bool(self.exit_sides) != bool(self.exit_reason and self.exit_reason.strip()):
            raise ValueError("provider exit sides and reason must be reported together")
        if self.backend_non_action_reason is not None and not (
            self.backend_non_action_reason.strip()
        ):
            raise ValueError(
                "backend non-action reason must be non-empty when reported"
            )
        if self.target_anchor is not None and (
            not math.isfinite(self.target_anchor) or self.target_anchor <= 0.0
        ):
            raise ValueError("provider target_anchor must be positive and finite")
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("provider confidence must be within [0, 1]")

    def as_payload(self) -> dict[str, object]:
        """Return exact signal facts and diagnostic readiness for the TUI."""
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "decision_time_ms": self.decision_time_ms,
            "reference_price": self.reference_price,
            "decision_action": self.decision_action,
            "eligible": self.eligible,
            "reason": self.reason,
            "side": self.side,
            "score": self.score,
            "minimum_score": self.minimum_score,
            "trigger": self.trigger,
            "primary_regime": self.primary_regime,
            "state_1m": self.state_1m,
            "state_5m": self.state_5m,
            "context_15m": self.context_15m,
            "confidence": self.confidence,
            "exit_sides": sorted(self.exit_sides),
            "exit_reason": self.exit_reason,
            "backend_non_action_reason": self.backend_non_action_reason,
            "target_anchor": self.target_anchor,
            "readiness": self.readiness.as_payload(),
        }


def build_hulk_bidirectional_intents(
    raw_bars: pd.DataFrame,
    *,
    symbol: str,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
    backtest_lab_root: Path,
    decision_builder: HulkDecisionBuilderProtocol = build_completed_hulk_decisions,
) -> tuple[StrategyIntent, ...]:
    """Return eligible Hulk-derived long and short intents for one symbol."""
    return collect_hulk_bidirectional_intents(
        raw_bars,
        symbol=symbol,
        observed_at=observed_at,
        after_decision_time_ms=after_decision_time_ms,
        backtest_lab_root=backtest_lab_root,
        decision_builder=decision_builder,
    ).intents


def collect_hulk_bidirectional_intents(
    raw_bars: pd.DataFrame,
    *,
    symbol: str,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
    backtest_lab_root: Path,
    decision_builder: HulkDecisionBuilderProtocol = build_completed_hulk_decisions,
) -> IntentBatch:
    """Return Hulk intents and advance through every completed decision."""
    decisions = decision_builder(
        raw_bars,
        observed_at=observed_at,
        config=_hulk_config(backtest_lab_root),
        after_decision_time_ms=after_decision_time_ms,
        allowed_sides=frozenset({"long", "short"}),
    )
    intents = tuple(
        _hulk_intent(decision, symbol)
        for decision in decisions
        if decision.entry_eligible
    )
    evaluations = tuple(_hulk_evaluation(decision, symbol) for decision in decisions)
    return IntentBatch(
        intents,
        _latest_boundary(decisions, after_decision_time_ms),
        evaluations,
    )


def build_range_onset_bidirectional_intents(
    raw_bars: pd.DataFrame,
    *,
    symbol: str,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
    entry_context_policies: Mapping[str, str] | None = None,
    decision_builder: RangeDecisionBuilderProtocol = build_completed_live_decisions,
) -> tuple[StrategyIntent, ...]:
    """Return range-onset long and short intents for one enabled symbol."""
    return collect_range_onset_bidirectional_intents(
        raw_bars,
        symbol=symbol,
        observed_at=observed_at,
        after_decision_time_ms=after_decision_time_ms,
        entry_context_policies=entry_context_policies,
        decision_builder=decision_builder,
    ).intents


def collect_range_onset_bidirectional_intents(
    raw_bars: pd.DataFrame,
    *,
    symbol: str,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None,
    entry_context_policies: Mapping[str, str] | None = None,
    decision_builder: RangeDecisionBuilderProtocol = build_completed_live_decisions,
) -> IntentBatch:
    """Return range-onset intents and advance through every completed bar."""
    decisions = decision_builder(
        raw_bars,
        observed_at=observed_at,
        after_decision_time_ms=after_decision_time_ms,
    )
    policy = (entry_context_policies or {}).get(symbol)
    evaluations = tuple(
        range_decision_evaluation(decision, symbol, policy) for decision in decisions
    )
    intents = tuple(
        intent
        for decision, evaluation in zip(decisions, evaluations, strict=True)
        if evaluation.eligible
        if (intent := _range_intent(decision, symbol)) is not None
    )
    return IntentBatch(
        intents,
        _latest_boundary(decisions, after_decision_time_ms),
        evaluations,
    )


def _hulk_evaluation(
    decision: HulkSmashLiveDecision,
    symbol: str,
) -> ProviderEvaluation:
    readiness = decision.readiness or _unavailable_readiness()
    side = decision.signal_side if decision.entry_eligible else readiness.side
    return ProviderEvaluation(
        strategy_id=_HULK_STRATEGY,
        symbol=symbol,
        decision_time_ms=decision.decision_time_ms,
        reference_price=decision.reference_price,
        decision_action=decision.decision_action,
        eligible=decision.entry_eligible,
        reason=decision.reason,
        side=side,
        readiness=readiness,
        score=decision.score,
        minimum_score=decision.minimum_score,
        trigger=decision.trigger,
    )


def range_decision_evaluation(
    decision: SolLiveDecision,
    symbol: str,
    entry_context_policy: str | None = None,
) -> ProviderEvaluation:
    """Project one canonical completed-bar decision into provider telemetry."""
    side = "long" if decision.long_entry else "short" if decision.short_entry else None
    readiness = _effective_range_readiness(decision, entry_context_policy)
    context_admitted = readiness.metrics.get("entry_context_admitted")
    eligible = side is not None and context_admitted is not False
    if entry_context_policy is not None:
        eligible = eligible and context_admitted is True
    reason = _range_reason(
        side=side,
        regime_admitted=decision.regime_admitted,
        entry_context_policy=entry_context_policy,
        context_admitted=context_admitted,
    )
    exit_sides = frozenset(
        side
        for side, exits in (
            ("long", decision.long_exit),
            ("short", decision.short_exit),
        )
        if exits
    )
    return ProviderEvaluation(
        strategy_id=_RANGE_STRATEGY,
        symbol=symbol,
        decision_time_ms=decision.decision_time_ms,
        reference_price=decision.reference_price,
        decision_action=decision.decision_action,
        eligible=eligible,
        reason=reason,
        side=side,
        readiness=readiness,
        primary_regime=decision.primary_regime,
        state_1m=decision.state_1m,
        state_5m=decision.state_5m,
        context_15m=decision.context_15m,
        confidence=decision.confidence,
        exit_sides=exit_sides,
        exit_reason="range_onset_signal" if exit_sides else None,
    )


def _range_reason(
    *,
    side: str | None,
    regime_admitted: bool,
    entry_context_policy: str | None,
    context_admitted: object,
) -> str:
    if side is None:
        return "entry_condition_absent" if regime_admitted else "regime_not_admitted"
    if entry_context_policy is None or context_admitted is True:
        return "entry_signal_present"
    state = "opposed" if context_admitted is False else "unavailable"
    return f"entry_context_dual_mtf_{state}"


def _effective_range_readiness(
    decision: SolLiveDecision,
    policy: str | None,
) -> SignalReadiness:
    source = decision.readiness or _unavailable_readiness()
    if policy is None:
        return source
    if policy != "dual_mtf_not_opposed":
        raise ValueError(f"unsupported range entry context policy: {policy}")
    admitted = source.metrics.get("dual_mtf_context_challenger_admitted")
    if not isinstance(admitted, bool):
        admitted = None
    state = "CLEAR" if admitted else "OPPOSED" if admitted is False else "UNAVAILABLE"
    blocker = (
        ()
        if admitted
        else (
            "dual_mtf_context_opposed"
            if admitted is False
            else "dual_mtf_context_unavailable",
        )
    )
    return SignalReadiness(
        side=source.side,
        conditions_met=source.conditions_met + int(admitted is True),
        conditions_required=source.conditions_required + 1,
        blockers=source.blockers + blocker,
        indicators=source.indicators + (f"ENTRY CONTEXT DUAL-MTF {state} [ACTIVE]",),
        metrics={
            **source.metrics,
            "entry_context_policy": policy,
            "entry_context_admitted": admitted,
            "entry_context_authority": "configured_execution",
        },
    )


def _unavailable_readiness() -> SignalReadiness:
    return SignalReadiness(
        side=None,
        conditions_met=0,
        conditions_required=1,
        blockers=("indicator_telemetry_unavailable",),
        indicators=("INDICATOR TELEMETRY UNAVAILABLE",),
    )


def _hulk_config(root: Path) -> HulkBidirectionalSourceConfig:
    profile = resolve_hulk_research_profile(_HULK_STRATEGY)
    return HulkBidirectionalSourceConfig(
        backtest_lab_root=root,
        supertrend_period=profile.supertrend_period,
        supertrend_multiplier=profile.supertrend_multiplier,
        adx_period=profile.adx_period,
        squeeze_period=profile.squeeze_period,
        minimum_score=profile.minimum_score,
        pivot_bars=profile.pivot_bars,
        adx_usable=profile.adx_usable,
        adx_trending=profile.adx_trending,
    )


def _hulk_intent(
    decision: HulkSmashLiveDecision,
    symbol: str,
) -> StrategyIntent:
    side = decision.signal_side
    if side not in {"long", "short"}:
        raise ValueError("eligible Hulk intent is missing a valid side")
    return StrategyIntent(
        strategy_id=_HULK_STRATEGY,
        symbol=symbol,
        side=side,
        decision_time_ms=decision.decision_time_ms,
        reference_price=decision.reference_price,
        reason=f"{decision.candidate}:{decision.trigger}",
        stop_anchor=decision.stop_anchor,
    )


def _range_intent(
    decision: SolLiveDecision,
    symbol: str,
) -> StrategyIntent | None:
    side = "long" if decision.long_entry else "short" if decision.short_entry else None
    if side is None:
        return None
    return StrategyIntent(
        strategy_id=_RANGE_STRATEGY,
        symbol=symbol,
        side=side,
        decision_time_ms=decision.decision_time_ms,
        reference_price=decision.reference_price,
        reason=f"{decision.decision_action}:{decision.primary_regime}",
    )


def _latest_boundary(
    decisions: tuple[HulkSmashLiveDecision, ...] | tuple[SolLiveDecision, ...],
    prior: int | None,
) -> int:
    if decisions:
        return decisions[-1].decision_time_ms
    return prior if prior is not None else 0
