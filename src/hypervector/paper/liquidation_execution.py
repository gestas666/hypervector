"""Explicit fill identity for the bounded shadow liquidation approximation."""

from __future__ import annotations

from typing import Any

from hypervector.paper.fill_models import FillResult

LIQUIDATION_FILL_MODEL = "liquidation_exact_mark_v1"
LIQUIDATION_EXECUTION_MODEL = "full_at_mark_shadow_approximation_v1"
PARTIAL_LIQUIDATION_THRESHOLD_USD = 100_000.0
PARTIAL_LIQUIDATION_SUPPORTED = False


class LiquidationExactMarkFillModel:
    """Close at the supplied mark without inventing separate slippage."""

    fill_model_id = LIQUIDATION_FILL_MODEL

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult:
        """Return the declared full-at-mark approximation."""
        del side, book, slippage_bps
        quantity = float(qty)
        return FillResult(
            fill_px=float(mark_px),
            fill_qty=quantity,
            fill_model_id=self.fill_model_id,
            levels_used=0,
            shortfall_qty=0.0,
            bbo_bid=None,
            bbo_ask=None,
            book_age_ms=None,
            fill_fallback_reason="full_at_mark_shadow_approximation",
            requested_qty=quantity,
        )
