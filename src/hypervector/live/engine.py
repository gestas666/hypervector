"""Live fill engine: optional venue place + live ledger (F3).

Warm-up uses place_enabled=False (synthetic position tracking, no venue).
Live phase sets place_enabled=True and stamps submitted from PlaceResult.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hypervector.live.exec_client import LiveExecClient, PlaceResult
from hypervector.live.ledger import append_live_decision
from hypervector.paper.costs import CostProvider, CostSnapshot, funding_payment
from hypervector.paper.order_intent import NETWORK_MAINNET, ORDER_INTENT_SCHEMA

logger = logging.getLogger(__name__)

_VALID_SIDES = frozenset({"buy", "sell"})


@dataclass
class LivePosition:
    qty: float = 0.0
    avg_px: float = 0.0
    realized_pnl: float = 0.0


def build_live_order_intent(
    *,
    symbol: str,
    side: str,
    qty: float,
    submit_enabled: bool,
    notes: str = "",
) -> dict[str, Any]:
    q = float(qty)
    if q <= 0:
        raise ValueError(f"qty must be positive, got {qty!r}")
    side_n = str(side).lower().strip()
    if side_n not in _VALID_SIDES:
        raise ValueError(f"side must be buy|sell, got {side!r}")
    return {
        "schema": ORDER_INTENT_SCHEMA,
        "network": NETWORK_MAINNET,
        "venue": "hyperliquid",
        "symbol": str(symbol),
        "side": side_n,
        "qty": q,
        "order_type": "market",
        "time_in_force": "ioc",
        "reduce_only": False,
        "client_ts_ms": time.time() * 1000.0,
        "submit_enabled": bool(submit_enabled),
        "notes": notes
        or ("live mainnet submit" if submit_enabled else "live warm-up no-submit"),
    }


class LiveFillEngine:
    """Position math + live ledger; places only when place_enabled and client set."""

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
        client: LiveExecClient | None = None,
        place_enabled: bool = False,
        max_notional_usd: float = 50.0,
    ) -> None:
        self._data_root = Path(data_root)
        self._cost_provider = cost_provider
        self._run_id = str(run_id)
        self._export_id = str(export_id)
        self._strategy_name = str(strategy_name)
        self._symbol = str(symbol)
        self._timeframe = str(timeframe)
        self._conviction = float(conviction)
        self._client = client
        self.place_enabled = bool(place_enabled)
        self._max_notional_usd = float(max_notional_usd)
        self._position = LivePosition()

    @property
    def position(self) -> LivePosition:
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
        conviction: float | None = None,
        conviction_source: str | None = None,
        metalabel_p: float | None = None,
        metalabel_bundle_id: str | None = None,
    ) -> dict[str, Any]:
        side_n = str(side).lower().strip()
        if side_n not in _VALID_SIDES:
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        qty_f = float(qty)
        if qty_f <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        mark = float(mark_px)
        if mark <= 0:
            raise ValueError(f"mark_px must be positive, got {mark_px}")

        # Hard cap: scale qty down to max notional (tiny default $50).
        cap = float(self._max_notional_usd)
        max_qty = cap / mark if mark > 0 and cap > 0 else 0.0
        scaled = False
        if max_qty > 0 and qty_f > max_qty + 1e-15:
            qty_f = max_qty
            scaled = True

        place_attempted = bool(self.place_enabled and self._client is not None)
        place_result: PlaceResult | None = None
        submit_error: str | None = None
        venue_order_id: str | None = None
        submitted = False

        if place_attempted:
            assert self._client is not None
            place_result = self._client.place_market(
                self._symbol, side_n, qty_f, mark_px=mark
            )
            submitted = bool(place_result.submitted)
            venue_order_id = place_result.venue_order_id
            submit_error = place_result.error
            if not submitted:
                # Reject: ledger honesty, no position update.
                record = self._base_record(
                    feed_ts=feed_ts,
                    action=str(action),
                    side=side_n,
                    qty=qty_f,
                    mark_px=mark,
                    fill_px=mark,
                    snap=self._cost_provider.snapshot(),
                    fee_usd=0.0,
                    funding_payment_usd=0.0,
                    conviction=conviction,
                    conviction_source=conviction_source,
                    metalabel_p=metalabel_p,
                    metalabel_bundle_id=metalabel_bundle_id,
                )
                record["submitted"] = False
                record["place_attempted"] = True
                record["live_phase"] = True
                record["venue_order_id"] = venue_order_id
                record["submit_error"] = submit_error
                record["qty_scaled_to_cap"] = scaled
                record["order_intent"] = build_live_order_intent(
                    symbol=self._symbol,
                    side=side_n,
                    qty=qty_f,
                    submit_enabled=True,
                )
                if intent is not None:
                    record["intent"] = intent
                append_live_decision(self._data_root, record)
                return record

        # Warm-up synthetic path OR successful place: update position.
        fill_px = mark
        snap = self._cost_provider.snapshot()
        fee_usd = abs(qty_f) * fill_px * self._cost_provider.trade_fee_rate()
        self._update_position(side=side_n, qty=qty_f, fill_px=fill_px, fee_usd=fee_usd)

        record = self._base_record(
            feed_ts=feed_ts,
            action=str(action),
            side=side_n,
            qty=qty_f,
            mark_px=mark,
            fill_px=fill_px,
            snap=snap,
            fee_usd=fee_usd,
            funding_payment_usd=0.0,
            conviction=conviction,
            conviction_source=conviction_source,
            metalabel_p=metalabel_p,
            metalabel_bundle_id=metalabel_bundle_id,
        )
        record["submitted"] = submitted
        record["place_attempted"] = place_attempted
        record["live_phase"] = place_attempted
        record["venue_order_id"] = venue_order_id
        record["submit_error"] = submit_error
        record["qty_scaled_to_cap"] = scaled
        record["order_intent"] = build_live_order_intent(
            symbol=self._symbol,
            side=side_n,
            qty=qty_f,
            submit_enabled=place_attempted,
        )
        if intent is not None:
            record["intent"] = intent
        append_live_decision(self._data_root, record)
        return record

    def apply_funding(
        self, *, feed_ts: Any, oracle_px: float, hours: float = 1.0
    ) -> dict | None:
        pos = self._position
        if pos.qty == 0.0:
            return None
        snap = self._cost_provider.snapshot()
        oracle = float(oracle_px)
        payment = funding_payment(
            position_qty=pos.qty,
            oracle_px=oracle,
            funding_rate_hourly=snap.funding_rate_hourly,
            hours=hours,
        )
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
        record["submitted"] = False
        record["place_attempted"] = False
        record["live_phase"] = bool(self.place_enabled)
        append_live_decision(self._data_root, record)
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
        conviction: float | None = None,
        conviction_source: str | None = None,
        metalabel_p: float | None = None,
        metalabel_bundle_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "execution_mode": "live",
            "network": NETWORK_MAINNET,
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
            "fill_model_id": "live_venue_v1"
            if self.place_enabled
            else "live_warm_synthetic_v1",
            "slippage_bps": snap.slippage_bps,
            "taker_fee": snap.taker_fee,
            "maker_fee": snap.maker_fee,
            "fee_usd": fee_usd,
            "funding_rate_hourly": snap.funding_rate_hourly,
            "funding_payment_usd": funding_payment_usd,
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
            "max_notional_usd": self._max_notional_usd,
        }

    def _update_position(
        self,
        *,
        side: str,
        qty: float,
        fill_px: float,
        fee_usd: float,
    ) -> None:
        """Update qty/avg_px/realized_pnl (same signed-qty convention as paper)."""
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
            pos.avg_px = (abs(pos.qty) * pos.avg_px + abs(signed) * fill_px) / abs(
                new_qty
            )
            pos.qty = new_qty
            return

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
        else:
            pos.qty = open_qty if signed > 0 else -open_qty
            pos.avg_px = fill_px
