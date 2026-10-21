"""Ledger-backed HYPE exact-one-blocker candidate intent provider."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.cohort_candidate_entry_clock import (
    AcceptedEntryClock,
    CandidateEntryClockStateError,
)
from hypervector.live.hype_breakout_cohort_provider import (
    HypeBreakoutOnsetCollector,
    HypeDecisionBuilderProtocol,
)
from hypervector.live.hype_relaxed_contract import (
    HYPE_RELAXED_FIXED_STRATEGY,
    HYPE_RELAXED_STRATEGIES,
    HYPE_RELAXED_TARGET20_STRATEGY,
    require_hype_relaxed_strategy,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness
from hypervector.live.sol_range_onset_decision_source import (
    build_completed_live_decisions,
)

HYPE_RELAXED_ONE_BLOCKER_STRATEGY = HYPE_RELAXED_FIXED_STRATEGY
HYPE_RELAXED_ONE_BLOCKER_STRATEGIES = HYPE_RELAXED_STRATEGIES
_EXACT_CANONICAL_BLOCKERS = ("5m_not_breakout",)
_FIXED_HOLD_MS = 60 * 60 * 1_000
_REARM_MS = 75 * 60 * 1_000
_MAXIMUM_ENTRY_AGE_MS = 60 * 1_000


HypeRelaxedOneBlockerStateError = CandidateEntryClockStateError


class HypeRelaxedOneBlockerCollector:
    """Emit exact-one-blocker entries with a 60m hold plus 15m re-entry buffer."""

    def __init__(
        self,
        *,
        decision_builder: HypeDecisionBuilderProtocol = build_completed_live_decisions,
        cohort_ledger: Path | None = None,
        strategy_id: str = HYPE_RELAXED_ONE_BLOCKER_STRATEGY,
    ) -> None:
        """Bind the canonical source and recover the last accepted entry."""
        self._strategy_id = require_hype_relaxed_strategy(strategy_id)
        self._canonical = HypeBreakoutOnsetCollector(
            decision_builder=decision_builder,
        )
        self._entry_clock = AcceptedEntryClock(
            cohort_ledger,
            strategy_id=self._strategy_id,
            symbol="HYPE",
        )
        self._highest_requested_boundary: int | None = None

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return causal readiness and at most one re-armed live intent."""
        if symbol != "HYPE":
            raise ValueError("relaxed one-blocker provider supports HYPE only")
        observed_ms = _aware_timestamp_ms(observed_at)
        boundary = _boundary(after_decision_time_ms)
        seed_query = self._is_seed_query(boundary)
        self._entry_clock.refresh()
        canonical = self._canonical(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        evaluations = self._candidate_evaluations(
            canonical.evaluations,
            observed_ms,
            seed_query,
        )
        intents = (
            ()
            if seed_query
            else tuple(_intent(row) for row in evaluations if row.eligible)
        )
        return IntentBatch(intents, canonical.latest_decision_time_ms, evaluations)

    def _candidate_evaluations(
        self,
        sources: tuple[ProviderEvaluation, ...],
        observed_ms: int,
        seed_query: bool,
    ) -> tuple[ProviderEvaluation, ...]:
        last_available_ms = self._entry_clock.latest_ms
        output: list[ProviderEvaluation] = []
        for source in sources:
            evaluation = self._candidate_evaluation(
                source,
                observed_ms,
                last_available_ms,
            )
            output.append(evaluation)
            if evaluation.eligible and not seed_query:
                last_available_ms = observed_ms
        return tuple(output)

    def _candidate_evaluation(
        self,
        source: ProviderEvaluation,
        observed_ms: int,
        last_available_ms: int | None,
    ) -> ProviderEvaluation:
        exact = (
            source.side in {"long", "short"}
            and source.readiness.blockers == _EXACT_CANONICAL_BLOCKERS
        )
        age_ms = observed_ms - source.decision_time_ms
        fresh = 0 <= age_ms <= _MAXIMUM_ENTRY_AGE_MS
        rearmed = (
            last_available_ms is None or observed_ms >= last_available_ms + _REARM_MS
        )
        eligible = exact and fresh and rearmed
        reason = _reason(exact, fresh, rearmed)
        readiness = _readiness(
            source,
            strategy_id=self._strategy_id,
            observed_ms=observed_ms,
            age_ms=age_ms,
            exact=exact,
            fresh=fresh,
            rearmed=rearmed,
            reason=reason,
            last_available_ms=last_available_ms,
        )
        return ProviderEvaluation(
            strategy_id=self._strategy_id,
            symbol=source.symbol,
            decision_time_ms=source.decision_time_ms,
            reference_price=source.reference_price,
            decision_action=f"enter_{source.side}" if eligible else "hold",
            eligible=eligible,
            reason=reason,
            side=source.side,
            readiness=readiness,
            trigger=_trigger(self._strategy_id) if eligible else "none",
            primary_regime=source.primary_regime,
            state_1m=source.state_1m,
            state_5m=source.state_5m,
            context_15m=source.context_15m,
            confidence=source.confidence,
        )

    def _is_seed_query(self, boundary: int) -> bool:
        prior = self._highest_requested_boundary
        seed_query = prior is not None and boundary < prior
        self._highest_requested_boundary = max(boundary, prior or 0)
        return seed_query


def _readiness(
    source: ProviderEvaluation,
    *,
    strategy_id: str,
    observed_ms: int,
    age_ms: int,
    exact: bool,
    fresh: bool,
    rearmed: bool,
    reason: str,
    last_available_ms: int | None,
) -> SignalReadiness:
    met = sum((exact, fresh, rearmed))
    blockers = () if met == 3 else (reason,)
    metrics: dict[str, ReadinessMetric] = {
        **source.readiness.metrics,
        "candidate_authority": "staged_profile_only",
        "canonical_blockers": ",".join(source.readiness.blockers),
        "exact_5m_not_breakout_only": exact,
        "entry_age_seconds": max(0.0, age_ms / 1_000.0),
        "maximum_entry_age_seconds": _MAXIMUM_ENTRY_AGE_MS / 1_000,
        "fixed_horizon_seconds": _FIXED_HOLD_MS / 1_000,
        "minimum_entry_spacing_seconds": _REARM_MS / 1_000,
        "exit_policy": _exit_policy(strategy_id),
        "target_bps": _target_bps(strategy_id),
        "last_candidate_available_time_ms": last_available_ms,
        "next_candidate_available_time_ms": (
            None if last_available_ms is None else last_available_ms + _REARM_MS
        ),
        "opi_execution_gate": False,
        "observed_at_ms": observed_ms,
    }
    return SignalReadiness(
        side=source.side,
        conditions_met=met,
        conditions_required=3,
        blockers=blockers,
        indicators=(
            f"EXACT 5M_NOT_BREAKOUT {'YES' if exact else 'NO'}",
            f"ENTRY AGE {max(0.0, age_ms / 1_000.0):.0f}s / 60s",
            f"75M ENTRY REARM {'READY' if rearmed else 'WAIT'}",
            _exit_indicator(strategy_id),
            "OPI REPORT ONLY / NO ENTRY GATE",
        ),
        metrics=metrics,
    )


def _reason(exact: bool, fresh: bool, rearmed: bool) -> str:
    if not exact:
        return "canonical_exact_one_blocker_absent"
    if not fresh:
        return "candidate_decision_stale"
    if not rearmed:
        return "fixed_horizon_rearm_active"
    return "exact_5m_not_breakout_rearmed"


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    if evaluation.side not in {"long", "short"}:
        raise ValueError("eligible relaxed HYPE candidate lacks a side")
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol=evaluation.symbol,
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"hype_exact_5m_not_breakout_60m_hold_15m_buffer:{evaluation.side}",
    )


def _exit_policy(strategy_id: str) -> str:
    return (
        "target20_then_60m"
        if strategy_id == HYPE_RELAXED_TARGET20_STRATEGY
        else "fixed_60m"
    )


def _target_bps(strategy_id: str) -> float | None:
    return 20.0 if strategy_id == HYPE_RELAXED_TARGET20_STRATEGY else None


def _exit_indicator(strategy_id: str) -> str:
    return (
        "EXIT TARGET 20BPS / 60M FALLBACK"
        if _target_bps(strategy_id)
        else "EXIT FIXED 60M"
    )


def _trigger(strategy_id: str) -> str:
    suffix = "target20" if _target_bps(strategy_id) else "fixed60"
    return f"exact_5m_not_breakout_75m_rearm_{suffix}"


def _aware_timestamp_ms(value: pd.Timestamp) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)


def _boundary(value: int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("after_decision_time_ms must be a nonnegative integer")
    return value
