"""Attach checkpoint-bound live evidence to the V58 research report."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.v58_execution_mandate_context import (
    ExecutionMandateContext,
    execution_mandate_context_payload,
)
from hypervector.research.v58_live_backend_context import (
    LiveBackendContext,
    live_backend_context_payload,
)
from hypervector.research.v58_venue_state_context import (
    VenueStateContext,
    venue_state_context_payload,
)


def attach_v58_continuous_live_contexts(
    report: dict[str, object],
    backend: LiveBackendContext,
    mandate: ExecutionMandateContext,
    venue: VenueStateContext,
) -> None:
    """Attach reconciled authority-none backend, venue, and mandate evidence."""
    _require_none_authority(backend, mandate, venue)
    _require_same_checkpoint(backend.evidence, mandate.evidence)
    payload = live_backend_context_payload(backend)
    payload.update(venue_state_context_payload(venue))
    report["live_backend_context"] = payload
    report["mandate_evidence"] = execution_mandate_context_payload(mandate)
    evidence = _evidence(report)
    evidence["live_backend_context"] = dict(backend.evidence)
    evidence["execution_mandate_context"] = dict(mandate.evidence)
    evidence["venue_state_context"] = dict(venue.evidence)


def _require_none_authority(
    backend: LiveBackendContext,
    mandate: ExecutionMandateContext,
    venue: VenueStateContext,
) -> None:
    if any(
        context.execution_authority != "none" for context in (backend, mandate, venue)
    ):
        raise ValueError("V58 live context has execution authority")


def _require_same_checkpoint(
    backend: Mapping[str, object], mandate: Mapping[str, object]
) -> None:
    if backend.get("checkpoint", backend) != mandate.get("checkpoint", mandate):
        raise ValueError("V58 backend and mandate checkpoint evidence differ")


def _evidence(report: dict[str, object]) -> dict[str, object]:
    evidence = report.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("V58 report evidence is invalid")
    return evidence
