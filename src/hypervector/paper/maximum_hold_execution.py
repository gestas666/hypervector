"""Fill identity for a fresh-BBO maximum-hold taker exit."""

from __future__ import annotations

from hypervector.execution import OrderCommand, VenueOrderEvent
from hypervector.paper.book import BookSnapshot
from hypervector.paper.fill_models import FillResult
from hypervector.paper.shadow_order_telemetry import timestamp
from hypervector.paper.order_intent import build_order_intent

MAXIMUM_HOLD_FILL_MODEL = "fresh_bbo_taker_v1"


class FreshBboTakerFillModel:
    """Apply a caller-validated fresh BBO price without a second price model."""

    fill_model_id = MAXIMUM_HOLD_FILL_MODEL

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: BookSnapshot | None,
        slippage_bps: float,
    ) -> FillResult:
        """Return the exact BBO fill already proven by the event shadow port."""
        del side, book, slippage_bps
        quantity = float(qty)
        return FillResult(
            fill_px=float(mark_px),
            fill_qty=quantity,
            fill_model_id=self.fill_model_id,
            levels_used=1,
            shortfall_qty=0.0,
            bbo_bid=None,
            bbo_ask=None,
            book_age_ms=None,
            fill_fallback_reason=None,
            requested_qty=quantity,
        )


def maximum_hold_order_intent(
    command: OrderCommand,
    event: VenueOrderEvent,
) -> dict[str, object]:
    """Describe the no-submit market IOC used by a maximum-hold exit."""
    return build_order_intent(
        symbol=command.symbol,
        side=command.side,
        qty=command.quantity,
        order_type="market",
        time_in_force="ioc",
        reduce_only=True,
        client_ts_ms=timestamp(event.event_at).timestamp() * 1_000,
        notes="shadow maximum-hold fresh-BBO taker exit; not sent",
    )
