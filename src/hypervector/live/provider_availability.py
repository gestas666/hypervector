"""Typed provider source unavailability and its fail-closed telemetry."""

from __future__ import annotations

from hypervector.live.provider_evaluation import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness


class ProviderSourceUnavailableError(ValueError):
    """A provider's external signal source cannot currently authorize entries.

    A collector raises this instead of returning an ``IntentBatch`` when a
    source it depends on is stale or missing; the poller records one explicit
    non-executable evaluation and does not advance the provider's cursor.
    """

    def __init__(self, reason: str) -> None:
        """Store a stable machine-readable non-action reason."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("provider source unavailability reason is required")
        self.reason = reason.strip()
        super().__init__(f"provider source unavailable: {self.reason}")


def unavailable_provider_evaluation(
    *,
    strategy_id: str,
    symbol: str,
    observed_ms: int,
    reference_price: float,
    reason: str,
) -> ProviderEvaluation:
    """Build explicit fail-closed telemetry without advancing a signal cursor."""
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol=symbol,
        decision_time_ms=observed_ms,
        reference_price=reference_price,
        decision_action="technical_unavailable",
        eligible=False,
        reason=reason,
        side=None,
        readiness=SignalReadiness(
            side=None,
            conditions_met=0,
            conditions_required=1,
            blockers=(reason,),
            indicators=("PROVIDER SOURCE UNAVAILABLE",),
            metrics={"technical_availability": "unavailable"},
        ),
        backend_non_action_reason=reason,
    )
