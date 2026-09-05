"""Typed HIP-3 availability failures and fail-closed telemetry."""

from __future__ import annotations

from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness


class Hip3ObserverUnavailableError(ValueError):
    """A report-only HIP-3 observer cannot currently authorize new entries."""

    def __init__(self, reason: str) -> None:
        """Store a stable machine-readable non-action reason."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("HIP-3 observer unavailability reason is required")
        self.reason = reason.strip()
        message = (
            "HIP-3 v3 observer status is stale"
            if self.reason == "observer_status_stale"
            else f"HIP-3 observer unavailable: {self.reason}"
        )
        super().__init__(message)


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
            indicators=("HIP-3 OBSERVER UNAVAILABLE",),
            metrics={"technical_availability": "unavailable"},
        ),
        backend_non_action_reason=reason,
    )
