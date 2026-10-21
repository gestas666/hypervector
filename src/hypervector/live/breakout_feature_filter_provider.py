"""Reusable causal feature filter around the canonical breakout provider."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hype_breakout_cohort_provider import HypeBreakoutOnsetCollector
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness


class CanonicalBreakoutCollectorProtocol(Protocol):
    """Canonical breakout source injected into a feature-filter provider."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return canonical completed-bar breakout evaluations."""
        ...


@dataclass(frozen=True)
class BreakoutFeatureFilterContract:
    """Immutable identity, thresholds, and telemetry for one filtered route."""

    strategy_id: str
    symbol: str
    trigger: str
    ready_reason: str
    intent_reason: str
    maximum_prior_bbwp_min_15m: float
    maximum_directional_body_bps: float
    stop_bps: float
    maximum_hold_seconds: int
    maximum_5m_bbwp_percentile: float | None = None
    hard_maximum_hold_seconds: int | None = None

    def __post_init__(self) -> None:
        """Reject incomplete identities, thresholds, and exit telemetry."""
        for label, value in (
            ("strategy_id", self.strategy_id),
            ("symbol", self.symbol),
            ("trigger", self.trigger),
            ("ready_reason", self.ready_reason),
            ("intent_reason", self.intent_reason),
        ):
            if not value.strip():
                raise ValueError(f"breakout feature filter {label} must be non-empty")
        for label, value in (
            ("prior BBWP", self.maximum_prior_bbwp_min_15m),
            ("directional body", self.maximum_directional_body_bps),
            ("stop", self.stop_bps),
        ):
            if not math.isfinite(value):
                raise ValueError(f"breakout feature filter {label} must be finite")
        optional = self.maximum_5m_bbwp_percentile
        if optional is not None and not 0.0 <= optional <= 100.0:
            raise ValueError("breakout feature filter 5m BBWP must be in [0, 100]")
        if self.maximum_hold_seconds <= 0:
            raise ValueError("breakout feature filter maximum hold must be positive")


class BreakoutFeatureFilterCollector:
    """Admit fresh canonical onsets only when every causal feature passes."""

    def __init__(
        self,
        contract: BreakoutFeatureFilterContract,
        *,
        canonical_collector: CanonicalBreakoutCollectorProtocol | None = None,
        execution_enabled: bool = False,
    ) -> None:
        """Bind one immutable filter contract and its explicit authority label."""
        if not isinstance(execution_enabled, bool):
            raise TypeError("breakout feature filter execution_enabled must be boolean")
        self._contract = contract
        self._canonical = canonical_collector or HypeBreakoutOnsetCollector()
        self._execution_enabled = execution_enabled

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return readiness and qualifying fresh intents for the bound symbol."""
        if symbol != self._contract.symbol:
            raise ValueError(
                f"{self._contract.symbol} breakout feature filter supports "
                f"{self._contract.symbol} only"
            )
        canonical = self._canonical(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        fresh = {
            (row.symbol, row.side, row.decision_time_ms) for row in canonical.intents
        }
        evaluations = tuple(
            _candidate_evaluation(row, fresh, self._contract, self._execution_enabled)
            for row in canonical.evaluations
        )
        intents = tuple(
            _intent(row, self._contract) for row in evaluations if row.eligible
        )
        return IntentBatch(intents, canonical.latest_decision_time_ms, evaluations)


def _candidate_evaluation(
    source: ProviderEvaluation,
    fresh: set[tuple[str, str | None, int]],
    contract: BreakoutFeatureFilterContract,
    execution_enabled: bool,
) -> ProviderEvaluation:
    flags = _filter_flags(source, fresh, contract)
    (
        canonical_ready,
        source_fresh,
        available,
        compression_5m,
        compression_1m,
        pullback,
    ) = flags
    eligible = all(
        (canonical_ready, source_fresh, compression_5m, compression_1m, pullback)
    )
    reason = _reason(
        canonical_ready,
        source_fresh,
        available,
        compression_5m,
        compression_1m,
        pullback,
        contract.ready_reason,
    )
    readiness = _readiness(
        source,
        contract,
        execution_enabled,
        canonical_ready and source_fresh,
        compression_5m,
        compression_1m,
        pullback,
        reason,
    )
    return _project_evaluation(source, contract, eligible, reason, readiness)


def _project_evaluation(
    source: ProviderEvaluation,
    contract: BreakoutFeatureFilterContract,
    eligible: bool,
    reason: str,
    readiness: SignalReadiness,
) -> ProviderEvaluation:
    """Project filtered evidence without altering canonical market context."""
    return ProviderEvaluation(
        strategy_id=contract.strategy_id,
        symbol=source.symbol,
        decision_time_ms=source.decision_time_ms,
        reference_price=source.reference_price,
        decision_action=f"enter_{source.side}" if eligible else "hold",
        eligible=eligible,
        reason=reason,
        side=source.side,
        readiness=readiness,
        trigger=contract.trigger if eligible else "none",
        primary_regime=source.primary_regime,
        state_1m=source.state_1m,
        state_5m=source.state_5m,
        context_15m=source.context_15m,
        confidence=source.confidence,
    )


def _filter_flags(
    source: ProviderEvaluation,
    fresh: set[tuple[str, str | None, int]],
    contract: BreakoutFeatureFilterContract,
) -> tuple[bool, bool, bool, bool, bool, bool]:
    metrics = source.readiness.metrics
    available = _features_available(metrics, contract)
    canonical_ready = source.eligible and source.side in {"long", "short"}
    source_fresh = (source.symbol, source.side, source.decision_time_ms) in fresh
    compression_5m = _passes_5m(metrics, contract, available)
    compression_1m = available and _number(metrics["prior_bbwp_min_15m"]) <= (
        contract.maximum_prior_bbwp_min_15m
    )
    pullback = available and _number(metrics["directional_bar_body_bps"]) <= (
        contract.maximum_directional_body_bps
    )
    return (
        canonical_ready,
        source_fresh,
        available,
        compression_5m,
        compression_1m,
        pullback,
    )


def _readiness(
    source: ProviderEvaluation,
    contract: BreakoutFeatureFilterContract,
    execution_enabled: bool,
    entry_ready: bool,
    compression_5m: bool,
    compression_1m: bool,
    pullback: bool,
    reason: str,
) -> SignalReadiness:
    checks = [entry_ready, compression_1m, pullback]
    if contract.maximum_5m_bbwp_percentile is not None:
        checks.insert(1, compression_5m)
    authority = "automatic_execution" if execution_enabled else "report_only"
    metrics: dict[str, ReadinessMetric] = {
        **source.readiness.metrics,
        "candidate_authority": authority,
        "entry_policy_authority": authority,
        "canonical_breakout_onset_fresh": entry_ready,
        "maximum_prior_bbwp_min_15m": contract.maximum_prior_bbwp_min_15m,
        "maximum_directional_body_bps": contract.maximum_directional_body_bps,
        "maximum_5m_bbwp_percentile": contract.maximum_5m_bbwp_percentile,
        "stop_bps": contract.stop_bps,
        "maximum_hold_seconds": contract.maximum_hold_seconds,
        "hard_maximum_hold_seconds": contract.hard_maximum_hold_seconds,
    }
    return SignalReadiness(
        side=source.side,
        conditions_met=sum(checks),
        conditions_required=len(checks),
        blockers=_blockers(
            entry_ready, compression_5m, compression_1m, pullback, reason
        ),
        indicators=_indicators(source, contract, entry_ready, authority),
        metrics=metrics,
    )


def _features_available(
    metrics: object,
    contract: BreakoutFeatureFilterContract,
) -> bool:
    if not hasattr(metrics, "get"):
        return False
    names = ["prior_bbwp_min_15m", "directional_bar_body_bps"]
    if contract.maximum_5m_bbwp_percentile is not None:
        names.append("authoritative_5m_bbwp_percentile")
    return all(_is_number(metrics.get(name)) for name in names)


def _passes_5m(
    metrics: object,
    contract: BreakoutFeatureFilterContract,
    available: bool,
) -> bool:
    threshold = contract.maximum_5m_bbwp_percentile
    if threshold is None:
        return True
    return (
        available and _number(metrics["authoritative_5m_bbwp_percentile"]) <= threshold
    )


def _reason(
    canonical: bool,
    fresh: bool,
    available: bool,
    compression_5m: bool,
    compression_1m: bool,
    pullback: bool,
    ready_reason: str,
) -> str:
    if not canonical:
        return "canonical_breakout_onset_absent"
    if not fresh:
        return "canonical_intent_not_fresh"
    if not available:
        return "entry_features_unavailable"
    if not compression_5m:
        return "authoritative_5m_compression_absent"
    if not compression_1m:
        return "prior_compression_absent"
    if not pullback:
        return "directional_pullback_absent"
    return ready_reason


def _blockers(
    entry_ready: bool,
    compression_5m: bool,
    compression_1m: bool,
    pullback: bool,
    reason: str,
) -> tuple[str, ...]:
    if reason == "entry_features_unavailable":
        return (reason,)
    blockers: list[str] = []
    if not entry_ready:
        blockers.append(reason)
    if not compression_5m:
        blockers.append("authoritative_5m_compression_absent")
    if not compression_1m:
        blockers.append("prior_compression_absent")
    if not pullback:
        blockers.append("directional_pullback_absent")
    return tuple(dict.fromkeys(blockers))


def _indicators(
    source: ProviderEvaluation,
    contract: BreakoutFeatureFilterContract,
    entry_ready: bool,
    authority: str,
) -> tuple[str, ...]:
    values = [f"FRESH 5M BREAKOUT {'YES' if entry_ready else 'NO'}"]
    if contract.maximum_5m_bbwp_percentile is not None:
        values.append(
            "5M BBWP "
            f"{_format_metric(source, 'authoritative_5m_bbwp_percentile')} / "
            f"{contract.maximum_5m_bbwp_percentile:.1f} MAX"
        )
    values.extend(
        (
            "PRIOR BBWP MIN "
            f"{_format_metric(source, 'prior_bbwp_min_15m')} / "
            f"{contract.maximum_prior_bbwp_min_15m:.1f} MAX",
            "DIRECTIONAL BODY "
            f"{_format_metric(source, 'directional_bar_body_bps')} / "
            f"{contract.maximum_directional_body_bps:.1f} MAX",
            "EXIT "
            f"{contract.stop_bps:.0f}BPS STOP "
            f"[{authority.replace('_', ' ').upper()}]",
        )
    )
    return tuple(values)


def _intent(
    evaluation: ProviderEvaluation,
    contract: BreakoutFeatureFilterContract,
) -> StrategyIntent:
    if evaluation.side not in {"long", "short"}:
        raise ValueError("eligible breakout feature filter lacks a side")
    return StrategyIntent(
        strategy_id=contract.strategy_id,
        symbol=contract.symbol,
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"{contract.intent_reason}:{evaluation.side}",
    )


def _number(value: ReadinessMetric) -> float:
    if not _is_number(value):
        raise ValueError("breakout feature filter value is unavailable")
    return float(value)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_metric(source: ProviderEvaluation, name: str) -> str:
    value = source.readiness.metrics.get(name)
    return "N/A" if not _is_number(value) else f"{float(value):.1f}"
