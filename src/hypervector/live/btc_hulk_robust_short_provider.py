"""Shared-cohort adapter for the frozen robust BTC Hulk short provider."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hulk_smash_live_decisions import (
    HulkDecisionConfigProtocol,
    HulkSmashLiveDecision,
    build_completed_hulk_decisions,
)
from hypervector.live.multi_asset_signal_source import (
    IntentBatch,
    ProviderEvaluation,
)
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.market_cipher_strategy_research import (
    resolve_hulk_research_profile,
)

HULK_ROBUST_SHORT_STRATEGY = "hulk_expansion_short_robust_v3"
HULK_TUNED_SHORT_STRATEGY = "hulk_expansion_short_tuned_v2"
HULK_SHORT_STRATEGIES = frozenset(
    {HULK_ROBUST_SHORT_STRATEGY, HULK_TUNED_SHORT_STRATEGY}
)


class HulkDecisionBuilderProtocol(Protocol):
    """Completed-bar decision boundary used by runtime and focused tests."""

    def __call__(
        self,
        raw_bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        config: HulkDecisionConfigProtocol,
        after_decision_time_ms: int | None,
        allowed_sides: frozenset[str],
    ) -> tuple[HulkSmashLiveDecision, ...]:
        """Return unseen decisions in chronological order."""
        ...


@dataclass(frozen=True)
class _RobustShortConfig:
    backtest_lab_root: Path
    supertrend_period: int
    supertrend_multiplier: float
    adx_period: int
    squeeze_period: int
    minimum_score: int
    pivot_bars: int
    adx_usable: float
    adx_trending: float


class HulkRobustShortCollector:
    """Collect one frozen BTC Hulk short profile for the shared router."""

    def __init__(
        self,
        *,
        backtest_lab_root: Path,
        strategy_id: str = HULK_ROBUST_SHORT_STRATEGY,
        decision_builder: HulkDecisionBuilderProtocol = build_completed_hulk_decisions,
    ) -> None:
        self._strategy_id = strategy_id
        self._config = _config(backtest_lab_root, strategy_id)
        self._decision_builder = decision_builder

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Collect one causal batch from completed five-minute source bars."""
        if symbol != "BTC":
            raise ValueError("robust Hulk short provider requires BTC")
        decisions = self._decision_builder(
            bars,
            observed_at=observed_at,
            config=self._config,
            after_decision_time_ms=after_decision_time_ms,
            allowed_sides=frozenset({"short"}),
        )
        return IntentBatch(
            intents=tuple(
                _intent(value, symbol, self._strategy_id)
                for value in decisions
                if value.entry_eligible
            ),
            latest_decision_time_ms=_latest(decisions, after_decision_time_ms),
            evaluations=tuple(
                _evaluation(value, symbol, self._strategy_id) for value in decisions
            ),
        )


def _config(root: Path, strategy_id: str) -> _RobustShortConfig:
    if strategy_id not in HULK_SHORT_STRATEGIES:
        raise ValueError(f"unsupported Hulk short strategy: {strategy_id}")
    profile = resolve_hulk_research_profile(strategy_id)
    if profile.side != "short":
        raise ValueError("Hulk short profile must remain short-only")
    return _RobustShortConfig(
        root,
        profile.supertrend_period,
        profile.supertrend_multiplier,
        profile.adx_period,
        profile.squeeze_period,
        profile.minimum_score,
        profile.pivot_bars,
        profile.adx_usable,
        profile.adx_trending,
    )


def _intent(
    decision: HulkSmashLiveDecision,
    symbol: str,
    strategy_id: str,
) -> StrategyIntent:
    if decision.signal_side != "short":
        raise ValueError("robust Hulk entry must remain short")
    return StrategyIntent(
        strategy_id=strategy_id,
        symbol=symbol,
        side="short",
        decision_time_ms=decision.decision_time_ms,
        reference_price=decision.reference_price,
        reason=f"{decision.candidate}:{decision.trigger}",
        stop_anchor=decision.stop_anchor,
    )


def _evaluation(
    decision: HulkSmashLiveDecision,
    symbol: str,
    strategy_id: str,
) -> ProviderEvaluation:
    readiness = decision.readiness or _unavailable_readiness()
    side = "short" if decision.entry_eligible else readiness.side
    return ProviderEvaluation(
        strategy_id=strategy_id,
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


def _unavailable_readiness() -> SignalReadiness:
    return SignalReadiness(
        side=None,
        conditions_met=0,
        conditions_required=1,
        blockers=("indicator_telemetry_unavailable",),
        indicators=("INDICATOR TELEMETRY UNAVAILABLE",),
    )


def _latest(
    decisions: tuple[HulkSmashLiveDecision, ...],
    prior: int | None,
) -> int:
    if decisions:
        return decisions[-1].decision_time_ms
    return 0 if prior is None else prior
