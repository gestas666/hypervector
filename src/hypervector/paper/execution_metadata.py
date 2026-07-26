"""Validated additive metadata for normalized shadow execution evidence."""

from __future__ import annotations

import json
from typing import Mapping

_ALLOWED_FIELDS = frozenset(
    {
        "client_order_id",
        "venue_order_id",
        "venue_event_type",
        "execution_model",
        "execution_data_source",
        "execution_evidence_fresh",
        "execution_event_freshness_ms",
        "execution_submit_latency_ms",
        "execution_cancel_latency_ms",
        "execution_queue_ahead_qty",
        "execution_requested_qty",
        "cumulative_filled_qty",
        "remaining_qty",
        "liquidity_side",
        "margin_model",
        "clearance_fee_usd",
        "liquidation_execution_model",
    }
)


def validated_execution_metadata(
    metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return JSON-safe additive fields or reject accounting-field collisions."""
    if metadata is None:
        return {}
    unsupported = sorted(set(metadata) - _ALLOWED_FIELDS)
    if unsupported:
        raise ValueError(f"unsupported execution metadata fields: {unsupported}")
    values = dict(metadata)
    try:
        json.dumps(values, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("execution metadata must be finite JSON data") from exc
    return values
