"""Provider-local startup readiness collection for a live cohort."""

from __future__ import annotations

from dataclasses import dataclass, replace
import pandas as pd

from hypervector.live.provider_availability import (
    ProviderSourceUnavailableError,
    unavailable_provider_evaluation,
)
from hypervector.live.multi_asset_poll_validation import validate_intent_batch
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_registration import ProviderIntentCollectorProtocol
from hypervector.live.provider_registry import provider_readiness_lookback_minutes

_PREACTIVATION_READINESS_REASON = "pre_activation_readiness_seed"
RECOVERY_SCAN_START_METRIC = "pre_activation_scan_start_ms"
RECOVERY_SCAN_END_METRIC = "pre_activation_scan_end_ms"


@dataclass(frozen=True)
class ReadinessSeedViews:
    """Restart-safe recovery evidence and latest setup telemetry."""

    recovery: ProviderEvaluation | None
    telemetry: ProviderEvaluation | None


def collect_provider_batch(
    collector: ProviderIntentCollectorProtocol,
    bars: pd.DataFrame,
    strategy_id: str,
    symbol: str,
    observed: pd.Timestamp,
    prior: int,
    observed_ms: int,
    unavailable_reference_price: float,
) -> IntentBatch | ProviderEvaluation:
    """Collect a provider batch or one explicit fail-closed evaluation."""
    try:
        return collector(
            bars,
            symbol=symbol,
            observed_at=observed,
            after_decision_time_ms=prior,
        )
    except ProviderSourceUnavailableError as error:
        return unavailable_provider_evaluation(
            strategy_id=strategy_id,
            symbol=symbol,
            observed_ms=observed_ms,
            reference_price=unavailable_reference_price,
            reason=error.reason,
        )


def collect_readiness_seed(
    collector: ProviderIntentCollectorProtocol,
    bars: pd.DataFrame,
    strategy_id: str,
    symbol: str,
    observed: pd.Timestamp,
    activation_boundary: int,
    unavailable_reference_price: float,
) -> ProviderEvaluation | None:
    """Return one non-executable startup row or explicit source unavailability."""
    return collect_readiness_seed_views(
        collector,
        bars,
        strategy_id,
        symbol,
        observed,
        activation_boundary,
        unavailable_reference_price,
    ).recovery


def collect_readiness_seed_views(
    collector: ProviderIntentCollectorProtocol,
    bars: pd.DataFrame,
    strategy_id: str,
    symbol: str,
    observed: pd.Timestamp,
    activation_boundary: int,
    unavailable_reference_price: float,
) -> ReadinessSeedViews:
    """Return distinct recovery and latest-state startup evaluations."""
    lookback_ms = provider_readiness_lookback_minutes(strategy_id) * 60 * 1_000
    seed_boundary = max(0, activation_boundary - lookback_ms)
    seed_observed = pd.Timestamp(activation_boundary, unit="ms", tz="UTC")
    try:
        batch = collector(
            bars,
            symbol=symbol,
            observed_at=seed_observed,
            after_decision_time_ms=seed_boundary,
        )
    except ProviderSourceUnavailableError as error:
        unavailable = unavailable_provider_evaluation(
            strategy_id=strategy_id,
            symbol=symbol,
            observed_ms=int(observed.timestamp() * 1_000),
            reference_price=unavailable_reference_price,
            reason=error.reason,
        )
        return ReadinessSeedViews(unavailable, unavailable)
    validate_intent_batch(
        batch,
        strategy_id,
        symbol,
        seed_boundary,
        activation_boundary,
    )
    recovery = _latest_recovery_evaluation(batch.evaluations)
    latest = max(
        batch.evaluations,
        key=lambda value: value.decision_time_ms,
        default=None,
    )
    return ReadinessSeedViews(
        _seed_or_none(recovery, batch.evaluations),
        _seed_or_none(latest, batch.evaluations),
    )


def _seed_or_none(
    value: ProviderEvaluation | None,
    evaluations: tuple[ProviderEvaluation, ...],
) -> ProviderEvaluation | None:
    return None if value is None else _as_recovery_seed(value, evaluations)


def _latest_recovery_evaluation(
    evaluations: tuple[ProviderEvaluation, ...],
) -> ProviderEvaluation | None:
    """Prefer the latest missed recipe exit over a later non-exit setup row."""
    exits = tuple(value for value in evaluations if value.exit_sides)
    candidates = exits or evaluations
    return max(candidates, key=lambda value: value.decision_time_ms, default=None)


def latest_startup_telemetry_evaluation(
    seed: ProviderEvaluation | None,
    fresh: tuple[ProviderEvaluation, ...],
) -> ProviderEvaluation | None:
    """Expose the latest setup state independently of restart-exit recovery."""
    rows = ((seed,) if seed is not None else ()) + fresh
    return max(rows, key=lambda row: row.decision_time_ms, default=None)


def preferred_startup_runtime_evaluation(
    seed: ProviderEvaluation | None,
    fresh: tuple[ProviderEvaluation, ...],
) -> ProviderEvaluation | None:
    """Prefer recovery exits for runtime while retaining fresh decisions."""
    rows = ((seed,) if seed is not None else ()) + fresh
    exits = tuple(row for row in rows if row.exit_sides)
    return max(exits or rows, key=lambda row: row.decision_time_ms, default=None)


def _as_recovery_seed(
    seed: ProviderEvaluation,
    evaluations: tuple[ProviderEvaluation, ...],
) -> ProviderEvaluation:
    """Attach the exact evaluated restart interval to a non-entry seed."""
    decision_times = tuple(value.decision_time_ms for value in evaluations)
    readiness = replace(
        seed.readiness,
        metrics={
            **seed.readiness.metrics,
            RECOVERY_SCAN_START_METRIC: min(decision_times),
            RECOVERY_SCAN_END_METRIC: max(decision_times),
        },
    )
    return replace(
        seed,
        readiness=readiness,
        backend_non_action_reason=_PREACTIVATION_READINESS_REASON,
    )
