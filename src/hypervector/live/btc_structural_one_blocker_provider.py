"""Causal BTC structural-continuation exact-one-blocker intent provider."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.btc_structural_contract import (
    BTC_STRUCTURAL_FIXED60_STRATEGY,
    require_btc_structural_strategy,
)
from hypervector.live.cohort_candidate_entry_clock import AcceptedEntryClock
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.multi_asset_signal_source import (
    collect_range_onset_bidirectional_intents,
)
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness

_SOURCE_STRATEGY = "range_onset_bidirectional_v1"
_EXACT_BLOCKERS = ("awaiting_hourly_sma_cross",)
_FIXED_HOLD_MS = 60 * 60 * 1_000
_REARM_MS = 75 * 60 * 1_000
_MAXIMUM_ENTRY_AGE_MS = 60 * 1_000


class RangeSourceCollectorProtocol(Protocol):
    """Callable contract for the canonical range-onset evaluation source."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch: ...


class BtcStructuralOneBlockerCollector:
    """Emit fresh BTC structural sides blocked only by the hourly cross."""

    def __init__(
        self,
        *,
        source_collector: RangeSourceCollectorProtocol = (
            collect_range_onset_bidirectional_intents
        ),
        cohort_ledger: Path | None = None,
        strategy_id: str = BTC_STRUCTURAL_FIXED60_STRATEGY,
    ) -> None:
        """Bind the canonical source and recover accepted-entry cadence."""
        self._strategy_id = require_btc_structural_strategy(strategy_id)
        self._source = source_collector
        self._entry_clock = AcceptedEntryClock(
            cohort_ledger,
            strategy_id=self._strategy_id,
            symbol="BTC",
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
        """Return causal readiness and at most one family entry per cadence."""
        if symbol != "BTC":
            raise ValueError("BTC structural provider supports BTC only")
        observed_ms = _aware_timestamp_ms(observed_at)
        boundary = _boundary(after_decision_time_ms)
        seed_query = self._is_seed_query(boundary)
        self._entry_clock.refresh()
        source = self._source(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        evaluations = self._candidate_evaluations(
            source.evaluations,
            observed_ms,
            seed_query,
        )
        intents = (
            ()
            if seed_query
            else tuple(_intent(row) for row in evaluations if row.eligible)
        )
        return IntentBatch(intents, source.latest_decision_time_ms, evaluations)

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
        side = source.readiness.side
        exact = (
            source.strategy_id == _SOURCE_STRATEGY
            and source.symbol == "BTC"
            and side in {"long", "short"}
            and source.readiness.blockers == _EXACT_BLOCKERS
        )
        age_ms = observed_ms - source.decision_time_ms
        fresh = 0 <= age_ms <= _MAXIMUM_ENTRY_AGE_MS
        rearmed = (
            last_available_ms is None or observed_ms >= last_available_ms + _REARM_MS
        )
        eligible = exact and fresh and rearmed
        reason = _reason(exact, fresh, rearmed)
        return ProviderEvaluation(
            strategy_id=self._strategy_id,
            symbol="BTC",
            decision_time_ms=source.decision_time_ms,
            reference_price=source.reference_price,
            decision_action=f"enter_{side}" if eligible else "hold",
            eligible=eligible,
            reason=reason,
            side=side if side in {"long", "short"} else None,
            readiness=_readiness(
                source,
                observed_ms=observed_ms,
                age_ms=age_ms,
                exact=exact,
                fresh=fresh,
                rearmed=rearmed,
                reason=reason,
                last_available_ms=last_available_ms,
            ),
            trigger=("exact_hourly_cross_blocker_fixed60" if eligible else "none"),
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
    observed_ms: int,
    age_ms: int,
    exact: bool,
    fresh: bool,
    rearmed: bool,
    reason: str,
    last_available_ms: int | None,
) -> SignalReadiness:
    metrics: dict[str, ReadinessMetric] = {
        **source.readiness.metrics,
        "candidate_authority": "staged_profile_only",
        "canonical_source_strategy_id": _SOURCE_STRATEGY,
        "canonical_blockers": ",".join(source.readiness.blockers),
        "exact_hourly_cross_blocker_only": exact,
        "entry_age_seconds": max(0.0, age_ms / 1_000.0),
        "maximum_entry_age_seconds": _MAXIMUM_ENTRY_AGE_MS / 1_000,
        "fixed_horizon_seconds": _FIXED_HOLD_MS / 1_000,
        "minimum_entry_spacing_seconds": _REARM_MS / 1_000,
        "exit_policy": "fixed_60m",
        "last_candidate_available_time_ms": last_available_ms,
        "next_candidate_available_time_ms": (
            None if last_available_ms is None else last_available_ms + _REARM_MS
        ),
        "opi_execution_gate": False,
        "observed_at_ms": observed_ms,
    }
    return SignalReadiness(
        side=source.readiness.side,
        conditions_met=sum((exact, fresh, rearmed)),
        conditions_required=3,
        blockers=() if exact and fresh and rearmed else (reason,),
        indicators=(
            f"EXACT HOURLY CROSS BLOCKER {'YES' if exact else 'NO'}",
            f"ENTRY AGE {max(0.0, age_ms / 1_000.0):.0f}s / 60s",
            f"75M ENTRY REARM {'READY' if rearmed else 'WAIT'}",
            "EXIT FIXED 60M",
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
    return "exact_hourly_cross_blocker_rearmed"


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    if evaluation.side not in {"long", "short"}:
        raise ValueError("eligible BTC structural candidate lacks a side")
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol="BTC",
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"btc_structural_fixed60_75m_rearm:{evaluation.side}",
    )


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
