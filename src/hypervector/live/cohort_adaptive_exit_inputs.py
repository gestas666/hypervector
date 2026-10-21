"""Freshness and causal input preparation for the adaptive exit policy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hypervector.cohort_profit_lock_policy import CandleLike
import math

from hypervector.live.canonical_regime_telemetry import latest_canonical_evaluation_at_or_before
from hypervector.live.cohort_adaptive_exit_policy import BOOK_MAX_AGE_MS
from hypervector.live.cohort_regime_routing import canonical_alignment_score
from hypervector.live.hyperliquid_protocol import HyperliquidBookSnapshot
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.live.provider_evaluation import ProviderEvaluation

MINUTE_MS = 60_000
CONTEXT_MAX_AGE_MS = 90_000
ATR_PERIOD = 20
ROUND_TRIP_COST_ASSUMPTION_BPS = 20.0


@dataclass(frozen=True)
class AdaptiveMarketInputs:
    """Causal market evidence with unavailable features retained as absent."""

    price: float | None
    price_source: str
    atr_bps: float | None
    alignment: float | None
    regime_ms: int | None
    book_ms: int | None
    signed_pressure: float | None
    friction_bps: float


def prepare_adaptive_inputs(
    *, symbol: str, side: str, entry_price: float, opened_ms: int, observed_ms: int,
    book: HyperliquidBookSnapshot | None, bars: tuple[CohortMarketBar, ...],
    evaluations: tuple[ProviderEvaluation, ...],
) -> AdaptiveMarketInputs:
    """Use only completed candles and fresh executable-side book prices."""
    completed = tuple(bar for bar in bars if bar.symbol == symbol and bar.timestamp_ms + MINUTE_MS <= observed_ms)
    fresh = completed and 0 <= observed_ms - completed[-1].timestamp_ms - MINUTE_MS <= CONTEXT_MAX_AGE_MS
    price = completed[-1].close if fresh and completed[-1].timestamp_ms + MINUTE_MS > opened_ms else None
    source = "completed_minute_close" if price is not None else "unavailable"
    valid_book = _fresh_book(book, observed_ms, opened_ms)
    stamp, pressure, spread = None, None, 0.0
    if valid_book and book is not None:
        price = book.bids[0].price if side == "long" else book.asks[0].price
        source, stamp = "executable_book_quote", book.exchange_timestamp_ms
        pressure = book.order_pressure * (1 if side == "long" else -1)
        spread = (book.asks[0].price - book.bids[0].price) / book.mid_price * 10_000
    regime = latest_canonical_evaluation_at_or_before(evaluations, symbol, observed_ms)
    if regime is not None and observed_ms - regime.decision_time_ms > CONTEXT_MAX_AGE_MS:
        regime = None
    alignment = canonical_alignment_score(side, regime) if regime is not None else None
    return AdaptiveMarketInputs(price, source, adaptive_atr_bps(completed, entry_price) if fresh else None,
                                alignment, regime.decision_time_ms if regime else None,
                                stamp, pressure, ROUND_TRIP_COST_ASSUMPTION_BPS + spread)


def _fresh_book(book: HyperliquidBookSnapshot | None, observed_ms: int, opened_ms: int) -> bool:
    if book is None or not book.bids or not book.asks:
        return False
    if not opened_ms <= book.exchange_timestamp_ms <= observed_ms:
        return False
    if observed_ms - book.exchange_timestamp_ms > BOOK_MAX_AGE_MS:
        return False
    positive = (book.bids[0].price, book.asks[0].price, book.bids[0].size,
                book.asks[0].size, book.mid_price, book.bid_depth, book.ask_depth)
    return (all(math.isfinite(value) and value > 0 for value in positive)
            and book.bids[0].price < book.asks[0].price
            and math.isfinite(book.order_pressure) and -1 <= book.order_pressure <= 1)


def adaptive_atr_bps(bars: Sequence[CandleLike], entry: float) -> float | None:
    """Return the exact completed-minute ATR used by live and replay paths."""
    recent = bars[-(ATR_PERIOD + 1):]
    if len(recent) != ATR_PERIOD + 1:
        return None
    pairs = tuple(zip(recent, recent[1:], strict=False))
    if any(right.timestamp_ms - left.timestamp_ms != MINUTE_MS for left, right in pairs):
        return None
    ranges = [max(right.high - right.low, abs(right.high - left.close),
                  abs(right.low - left.close)) for left, right in pairs]
    return sum(ranges) / ATR_PERIOD / entry * 10_000
