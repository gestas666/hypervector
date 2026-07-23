"""Explicit paper fills: FillModel-driven prices + funding rows.

Pure position math + decision append. No live orders.
Optional sandbox_enabled is shadow-only (no Nautilus sandbox client in Phase 3).
Preferred default is l2_walk_v1; missing/stale book falls back to bar_close.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from hypervector.paper.costs import CostProvider, CostSnapshot, funding_payment
from hypervector.paper.fill_models import (
    DEFAULT_MAX_BOOK_AGE_MS,
    FILL_MODEL_L2_WALK_V1,
    FillModel,
    FillResult,
    select_fill_model,
)
from hypervector.paper.ledger import append_paper_decision

logger = logging.getLogger(__name__)

_VALID_SIDES = frozenset({"buy", "sell"})


@dataclass
class PaperPosition:
    """Paper portfolio state (qty signed: long > 0, short < 0)."""

    qty: float = 0.0
    avg_px: float = 0.0
    realized_pnl: float = 0.0


class ExplicitFillEngine:
    """Apply market fills and funding to a paper position; append decisions."""

    def __init__(
        self,
        data_root: Path | str,
        *,
        cost_provider: CostProvider,
        run_id: str,
        export_id: str,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        conviction: float,
        sandbox_enabled: bool = False,
        preferred_fill_model: str = FILL_MODEL_L2_WALK_V1,
        max_book_age_ms: float = DEFAULT_MAX_BOOK_AGE_MS,
    ) -> None:
        self._data_root = Path(data_root)
        self._cost_provider = cost_provider
        self._run_id = str(run_id)
        self._export_id = str(export_id)
        self._strategy_name = str(strategy_name)
        self._symbol = str(symbol)
        self._timeframe = str(timeframe)
        self._conviction = float(conviction)
        self._sandbox_enabled = bool(sandbox_enabled)
        self._preferred_fill_model = str(preferred_fill_model)
        self._max_book_age_ms = float(max_book_age_ms)
        self._position = PaperPosition()
        if self._sandbox_enabled:
            # Real Nautilus Sandbox client is Phase 4/hardening; flag + shadow keys only.
            logger.info("sandbox_requested_but_not_wired")

    @property
    def position(self) -> PaperPosition:
        return self._position

    def apply_market_fill(
        self,
        *,
        feed_ts: Any,
        action: str,
        side: str,
        qty: float,
        mark_px: float,
        intent: dict | None = None,
        book: Any | None = None,
        fill_model: FillModel | None = None,
        now_ms: float | None = None,
        conviction: float | None = None,
        conviction_source: str | None = None,
        metalabel_p: float | None = None,
        metalabel_bundle_id: str | None = None,
    ) -> dict:
        side_n = str(side).lower().strip()
        if side_n not in _VALID_SIDES:
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        qty_f = float(qty)
        if qty_f <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        mark = float(mark_px)
        if mark <= 0:
            raise ValueError(f"mark_px must be positive, got {mark_px}")

        snap = self._cost_provider.snapshot()
        if fill_model is not None:
            model: FillModel = fill_model
            fallback_reason: str | None = None
        else:
            model, fallback_reason = select_fill_model(
                preferred=self._preferred_fill_model,
                book=book,
                max_book_age_ms=self._max_book_age_ms,
                now_ms=now_ms,
            )
        result = model.fill(
            side=side_n,
            qty=qty_f,
            mark_px=mark,
            book=book,
            slippage_bps=float(snap.slippage_bps),
        )
        if fallback_reason is not None and result.fill_fallback_reason is None:
            result = replace(result, fill_fallback_reason=fallback_reason)
        fill_px = float(result.fill_px)
        fill_qty = float(result.fill_qty)

        # L2 / TopBps may return fill_qty=0 when required side has no depth —
        # never invent liquidity; keep position flat but **ledger the skip**
        # so shortfall / model id remain auditable (SRS_HV4A_LOG).
        if fill_qty <= 0:
            logger.warning(
                "fill skipped: zero fill_qty model=%s side=%s requested=%s shortfall=%s",
                result.fill_model_id,
                side_n,
                qty_f,
                result.shortfall_qty,
            )
            skipped = self._base_record(
                feed_ts=feed_ts,
                action=str(action),
                side=side_n,
                qty=0.0,
                mark_px=mark,
                fill_px=fill_px,
                snap=snap,
                fee_usd=0.0,
                funding_payment_usd=0.0,
                fill_result=result,
                conviction=conviction,
                conviction_source=conviction_source,
                metalabel_p=metalabel_p,
                metalabel_bundle_id=metalabel_bundle_id,
            )
            skipped["qty"] = 0.0
            skipped["fill_qty"] = 0.0
            skipped["skipped"] = True
            skipped["requested_qty"] = float(result.requested_qty)
            skipped["shortfall_qty"] = float(result.shortfall_qty)
            if intent is not None:
                skipped["intent"] = intent
            append_paper_decision(self._data_root, skipped)
            return skipped

        fee_usd = abs(fill_qty) * fill_px * self._cost_provider.trade_fee_rate()
        self._update_position(side=side_n, qty=fill_qty, fill_px=fill_px, fee_usd=fee_usd)

        record = self._base_record(
            feed_ts=feed_ts,
            action=str(action),
            side=side_n,
            qty=fill_qty,
            mark_px=mark,
            fill_px=fill_px,
            snap=snap,
            fee_usd=fee_usd,
            funding_payment_usd=0.0,
            fill_result=result,
            conviction=conviction,
            conviction_source=conviction_source,
            metalabel_p=metalabel_p,
            metalabel_bundle_id=metalabel_bundle_id,
        )
        if intent is not None:
            record["intent"] = intent
        append_paper_decision(self._data_root, record)
        return record

    def apply_funding(self, *, feed_ts: Any, oracle_px: float) -> dict | None:
        """Apply one hour of funding on open position; return decision or None if flat."""
        pos = self._position
        if pos.qty == 0.0:
            return None

        snap = self._cost_provider.snapshot()
        oracle = float(oracle_px)
        payment = funding_payment(
            position_qty=pos.qty,
            oracle_px=oracle,
            funding_rate_hourly=snap.funding_rate_hourly,
            hours=1.0,
        )
        # Positive payment = cash paid by position holder (drag on realized pnl).
        pos.realized_pnl -= payment

        side = "buy" if pos.qty > 0 else "sell"
        record = self._base_record(
            feed_ts=feed_ts,
            action="funding",
            side=side,
            qty=abs(pos.qty),
            mark_px=oracle,
            fill_px=oracle,
            snap=snap,
            fee_usd=0.0,
            funding_payment_usd=payment,
        )
        append_paper_decision(self._data_root, record)
        return record

    def _base_record(
        self,
        *,
        feed_ts: Any,
        action: str,
        side: str,
        qty: float,
        mark_px: float,
        fill_px: float,
        snap: CostSnapshot,
        fee_usd: float,
        funding_payment_usd: float,
        fill_result: FillResult | None = None,
        conviction: float | None = None,
        conviction_source: str | None = None,
        metalabel_p: float | None = None,
        metalabel_bundle_id: str | None = None,
    ) -> dict:
        # Actual model from FillResult overwrites CostSnapshot fill_model_id when present.
        fill_model_id = (
            fill_result.fill_model_id if fill_result is not None else snap.fill_model_id
        )
        record: dict[str, Any] = {
            "execution_mode": "paper",
            "feed_ts": feed_ts,
            "run_id": self._run_id,
            "export_id": self._export_id,
            "strategy_name": self._strategy_name,
            "symbol": self._symbol,
            "timeframe": self._timeframe,
            "action": action,
            "side": side,
            "qty": qty,
            "mark_px": mark_px,
            "fill_px": fill_px,
            "fill_model_id": fill_model_id,
            "slippage_bps": snap.slippage_bps,
            "taker_fee": snap.taker_fee,
            "maker_fee": snap.maker_fee,
            "fee_usd": fee_usd,
            "funding_rate_hourly": snap.funding_rate_hourly,
            "funding_payment_usd": funding_payment_usd,
            "costs_source": _costs_source(snap),
            "sandbox_enabled": self._sandbox_enabled,
            # Shadow only — explicit fill_px remains ledger truth (sandbox client Phase 4).
            "sandbox_fill_px": None,
            "conviction": (
                float(conviction) if conviction is not None else self._conviction
            ),
            "conviction_source": (
                conviction_source if conviction_source is not None else "fixed"
            ),
            "metalabel_p": metalabel_p,
            "metalabel_bundle_id": metalabel_bundle_id,
            "position_qty": self._position.qty,
            "position_avg_px": self._position.avg_px,
            "realized_pnl": self._position.realized_pnl,
        }
        if fill_result is not None:
            # Merge all FillResult fields; fill_model_id / fill_px already set above.
            for key, value in asdict(fill_result).items():
                record[key] = value
            # Keep ledger qty aligned with filled qty (bar_close: same as requested).
            record["qty"] = fill_result.fill_qty
            record["fill_px"] = fill_result.fill_px
            record["fill_model_id"] = fill_result.fill_model_id
        return record

    def _update_position(
        self,
        *,
        side: str,
        qty: float,
        fill_px: float,
        fee_usd: float,
    ) -> None:
        """Update qty/avg_px/realized_pnl for a market fill (signed qty convention)."""
        pos = self._position
        signed = qty if side == "buy" else -qty
        pos.realized_pnl -= fee_usd

        if pos.qty == 0.0:
            pos.qty = signed
            pos.avg_px = fill_px
            return

        same_direction = (pos.qty > 0 and signed > 0) or (pos.qty < 0 and signed < 0)
        if same_direction:
            new_qty = pos.qty + signed
            pos.avg_px = (
                abs(pos.qty) * pos.avg_px + abs(signed) * fill_px
            ) / abs(new_qty)
            pos.qty = new_qty
            return

        # Opposite direction: reduce / close / flip
        close_qty = min(abs(signed), abs(pos.qty))
        if pos.qty > 0:
            pos.realized_pnl += close_qty * (fill_px - pos.avg_px)
        else:
            pos.realized_pnl += close_qty * (pos.avg_px - fill_px)

        remaining = abs(pos.qty) - close_qty
        open_qty = abs(signed) - close_qty
        if remaining == 0.0 and open_qty == 0.0:
            pos.qty = 0.0
            pos.avg_px = 0.0
        elif remaining > 0.0:
            pos.qty = remaining if pos.qty > 0 else -remaining
            # avg_px unchanged on partial close
        else:
            pos.qty = open_qty if signed > 0 else -open_qty
            pos.avg_px = fill_px


def _costs_source(snap: CostSnapshot) -> str:
    """Map snapshot provenance to schema costs_source label."""
    funding = (snap.sources or {}).get("funding", "unset")
    if funding.startswith("live"):
        return "live_funding"
    return "config"
