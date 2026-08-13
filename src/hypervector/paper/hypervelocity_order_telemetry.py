"""Ledger metadata for Hypervelocity shadow order and fill events."""

from __future__ import annotations

import pandas as pd

from hypervector.execution import OrderCommand, VenueOrderEvent
from hypervector.paper.shadow_execution_models import (
    ShadowExecutionRecord,
    ShadowOrderTelemetry,
)


def fill_metadata(
    event: VenueOrderEvent,
    evidence: ShadowExecutionRecord,
    *,
    liquidation_price: float | None,
) -> dict[str, object]:
    """Return durable causal evidence for one normalized fill."""
    return {
        "client_order_id": event.client_order_id,
        "venue_order_id": event.venue_order_id,
        "venue_event_type": event.event_type,
        "execution_model": evidence.execution_model,
        "execution_data_source": evidence.data_source,
        "execution_evidence_fresh": evidence.evidence_fresh,
        "execution_event_freshness_ms": evidence.event_freshness_ms,
        "execution_submit_latency_ms": evidence.configured_latency_ms,
        "execution_queue_ahead_qty": evidence.queue_ahead_quantity,
        "execution_requested_qty": evidence.requested_quantity,
        "cumulative_filled_qty": evidence.cumulative_filled_quantity,
        "remaining_qty": evidence.remaining_quantity,
        "liquidity_side": evidence.liquidity_side,
        "margin_model": evidence.margin_model,
        "liquidation_price": liquidation_price,
    }


def order_metadata(
    event: VenueOrderEvent,
    telemetry: ShadowOrderTelemetry,
    *,
    liquidation_price: float | None,
) -> dict[str, object]:
    """Return durable execution state for one normalized order event."""
    return {
        "client_order_id": event.client_order_id,
        "venue_order_id": event.venue_order_id,
        "venue_event_type": event.event_type,
        "execution_model": telemetry.execution_model,
        "execution_data_source": telemetry.data_source,
        "execution_evidence_fresh": telemetry.evidence_fresh,
        "execution_submit_latency_ms": telemetry.configured_submit_latency_ms,
        "execution_cancel_latency_ms": telemetry.configured_cancel_latency_ms,
        "execution_queue_ahead_qty": telemetry.queue_ahead_quantity,
        "cumulative_filled_qty": telemetry.cumulative_filled_quantity,
        "remaining_qty": telemetry.remaining_quantity,
        "margin_model": telemetry.margin_model,
        "liquidation_price": liquidation_price,
    }


def order_action(command: OrderCommand, event: VenueOrderEvent) -> str:
    """Return the stable ledger action for an order state transition."""
    role = command.order_role
    if event.event_type == "submitted":
        return f"submit_{role}"
    if event.event_type in {"canceled", "expired"}:
        return f"cancel_{role}"
    return f"{event.event_type}_{role}"


def timestamp(value: str) -> pd.Timestamp:
    """Return a pandas timestamp for legacy pending-entry projection."""
    return pd.Timestamp(value)
