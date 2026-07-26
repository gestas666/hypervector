"""Explicit fill identity for the bounded shadow liquidation approximation."""

from __future__ import annotations

from typing import Any

from hypervector.paper.fill_models import FillResult

LIQUIDATION_FILL_MODEL = "liquidation_l2_vwap_v2"
LIQUIDATION_EXECUTION_MODEL = "hyperliquid_market_liquidation_v2"
PARTIAL_LIQUIDATION_THRESHOLD_USD = 100_000.0
PARTIAL_LIQUIDATION_FRACTION = 0.20
LIQUIDATION_COOLDOWN_MS = 30_000
PARTIAL_LIQUIDATION_SUPPORTED = True
BACKSTOP_MAINTENANCE_FRACTION = 2.0 / 3.0
BACKSTOP_LIQUIDATION_SUPPORTED = True


class LiquidationExactMarkFillModel:
    """Apply a precomputed displayed-depth VWAP supplied as the mark argument."""

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
        """Return the caller-validated liquidation VWAP."""
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
            fill_fallback_reason=None,
            requested_qty=quantity,
        )
