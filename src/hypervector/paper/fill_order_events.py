"""Non-fill order lifecycle ledger behavior for the paper engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from hypervector.paper.costs import CostProvider
from hypervector.paper.execution_metadata import validated_execution_metadata
from hypervector.paper.ledger import append_paper_decision


class OrderEventLedgerMixin:
    """Append normalized order transitions without mutating a position."""

    _cost_provider: CostProvider
    _data_root: Path

    def record_order_event(
        self,
        *,
        feed_ts: Any,
        action: str,
        side: str,
        qty: float,
        limit_px: float,
        status: str,
        reason: str | None = None,
        conviction: float | None = None,
        conviction_source: str | None = None,
        metalabel_p: float | None = None,
        metalabel_bundle_id: str | None = None,
        record_metadata: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Append a non-fill maker order lifecycle event to the paper ledger."""
        execution_metadata = validated_execution_metadata(record_metadata)
        snap = self._cost_provider.snapshot()
        record = self._base_record(
            feed_ts=feed_ts,
            action=action,
            side=side,
            qty=0.0,
            mark_px=limit_px,
            fill_px=limit_px,
            snap=snap,
            fee_usd=0.0,
            funding_payment_usd=0.0,
            conviction=conviction,
            conviction_source=conviction_source,
            metalabel_p=metalabel_p,
            metalabel_bundle_id=metalabel_bundle_id,
        )
        record.update(
            {
                "fill_qty": 0.0,
                "requested_qty": float(qty),
                "order_status": str(status),
                "order_intent": self._order_intent(
                    side=side,
                    qty=qty,
                    mark_px=limit_px,
                    action="close" if action == "submit_target" else action,
                ),
            }
        )
        if reason is not None:
            record["reason"] = str(reason)
        record.update(execution_metadata)
        append_paper_decision(self._data_root, record)
        return record
