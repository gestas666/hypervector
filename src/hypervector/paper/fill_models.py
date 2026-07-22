"""FillModel protocol and bar_close_slippage_v1 (Phase 4a extraction).

Book-based models (top_bps / l2_walk) land in later tasks; select_fill_model
scaffolds fallback to bar_close when preferred is bar_close or book is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1 = "bar_close_slippage_v1"
FILL_MODEL_TOP_BPS_V1 = "top_bps_v1"
FILL_MODEL_L2_WALK_V1 = "l2_walk_v1"
DEFAULT_MAX_BOOK_AGE_MS = 3000


@dataclass(frozen=True)
class FillResult:
    fill_px: float
    fill_qty: float
    fill_model_id: str
    levels_used: int
    shortfall_qty: float
    bbo_bid: float | None
    bbo_ask: float | None
    book_age_ms: float | None
    fill_fallback_reason: str | None
    requested_qty: float


class FillModel(Protocol):
    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult: ...


class BarCloseSlippageFillModel:
    """Mark ± slippage_bps; no book dependency."""

    fill_model_id = FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult:
        slip = float(slippage_bps) / 10_000.0
        side_n = side.lower().strip()
        if side_n == "buy":
            px = float(mark_px) * (1.0 + slip)
        else:
            px = float(mark_px) * (1.0 - slip)
        q = float(qty)
        return FillResult(
            fill_px=px,
            fill_qty=q,
            fill_model_id=self.fill_model_id,
            levels_used=0,
            shortfall_qty=0.0,
            bbo_bid=None,
            bbo_ask=None,
            book_age_ms=None,
            fill_fallback_reason=None,
            requested_qty=q,
        )


def select_fill_model(
    *,
    preferred: str,
    book: Any | None,
    max_book_age_ms: float,
    now_ms: float | None = None,
) -> tuple[FillModel, str | None]:
    """Pick a fill model; Task 1 scaffold: bar_close or unusable book → bar_close.

    Returns (model, fill_fallback_reason). Reason is ``book_missing`` when
    preferred is not bar_close and book is None. Stale/top_bps/l2_walk selection
    is implemented in later tasks; ``max_book_age_ms`` / ``now_ms`` reserved.
    """
    _ = max_book_age_ms, now_ms  # reserved for stale-book checks (later tasks)
    preferred_n = str(preferred).strip()
    if preferred_n == FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1:
        return BarCloseSlippageFillModel(), None
    if book is None:
        return BarCloseSlippageFillModel(), "book_missing"
    # Book present but book models not wired yet → still bar_close (no silent switch)
    return BarCloseSlippageFillModel(), None
