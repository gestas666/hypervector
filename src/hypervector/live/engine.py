"""Live fill engine: optional venue place + live ledger (F3).

Warm-up uses place_enabled=False (synthetic position tracking, no venue).
Live phase sets place_enabled=True and stamps submitted from PlaceResult.
Synthetic exposure is discarded before arming, every live position change uses
the venue-reported fill, and the venue position is re-read after every live
order so an ambiguous fill or a second owner of the coin stops the daemon; a
matching read is adopted so float residue never reaches the next order size.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hypervector.live.exec_client import LiveExecClient, PlaceResult
from hypervector.live.ledger import append_live_decision
from hypervector.live.policy import notional_cap_error
from hypervector.paper.costs import CostProvider, CostSnapshot, funding_payment
from hypervector.paper.order_intent import NETWORK_MAINNET, ORDER_INTENT_SCHEMA

logger = logging.getLogger(__name__)

_VALID_SIDES = frozenset({"buy", "sell"})
# Float residue below this after netting is treated as flat.
_DUST_QTY = 1e-12
# Venue sizes are exact decimals at szDecimals <= 6; anything wider is real drift.
_RECONCILE_ABS_TOL = 1e-9


class LiveReconciliationError(RuntimeError):
    """Venue position disagrees with the engine after a live order (technical)."""


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
    reduce_only: bool = False,
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
        "reduce_only": bool(reduce_only),
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
        cap_error = notional_cap_error(max_notional_usd)
        if cap_error is not None:
            raise ValueError(cap_error)
        self._client = client
        self.place_enabled = bool(place_enabled)
        self._max_notional_usd = float(max_notional_usd)
        self._position = LivePosition()

    @property
    def position(self) -> LivePosition:
        return self._position

    def discard_synthetic_position(self) -> LivePosition:
        """Drop warm-up synthetic exposure before arming; return what was dropped.

        Only an unarmed engine holds synthetic exposure. An armed engine's
        position mirrors venue fills and is never discarded.
        """
        if self.place_enabled:
            raise RuntimeError("refusing to discard the position of an armed engine")
        previous = LivePosition(
            qty=self._position.qty,
            avg_px=self._position.avg_px,
            realized_pnl=self._position.realized_pnl,
        )
        self._position = LivePosition()
        return previous

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
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Apply one market decision; ``reduce_only`` marks a position close.

        Opening orders are scaled down to the hard notional cap. A reduce-only
        close is bounded by the position itself, so it is never cap-scaled into
        a partial close that would leave exposure behind.
        """
        side_n = str(side).lower().strip()
        if side_n not in _VALID_SIDES:
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        qty_f = float(qty)
        if not math.isfinite(qty_f) or qty_f <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        mark = float(mark_px)
        # NaN compares false against every bound and would skip the cap scaling.
        if not math.isfinite(mark) or mark <= 0:
            raise ValueError(f"mark_px must be positive, got {mark_px}")

        # Hard cap: scale opening qty down to max notional (tiny default $50).
        cap = float(self._max_notional_usd)
        max_qty = cap / mark
        scaled = False
        if not reduce_only and qty_f > max_qty + 1e-15:
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
                self._symbol,
                side_n,
                qty_f,
                mark_px=mark,
                reduce_only=bool(reduce_only),
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
                record["filled_qty"] = 0.0
                record["order_intent"] = build_live_order_intent(
                    symbol=self._symbol,
                    side=side_n,
                    qty=qty_f,
                    submit_enabled=True,
                    reduce_only=reduce_only,
                )
                if intent is not None:
                    record["intent"] = intent
                append_live_decision(self._data_root, record)
                self._reconcile_with_venue(feed_ts=feed_ts)
                return record

        # Warm-up synthetic path OR successful place: update position with the
        # venue-reported fill when the transport reports one.
        fill_qty = qty_f
        fill_px = mark
        if place_result is not None:
            if place_result.filled_qty is not None:
                fill_qty = float(place_result.filled_qty)
            if place_result.avg_px is not None:
                fill_px = float(place_result.avg_px)
        snap = self._cost_provider.snapshot()
        fee_usd = abs(fill_qty) * fill_px * self._cost_provider.trade_fee_rate()
        if fill_qty > 0.0:
            self._update_position(
                side=side_n, qty=fill_qty, fill_px=fill_px, fee_usd=fee_usd
            )

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
        record["filled_qty"] = fill_qty
        record["order_intent"] = build_live_order_intent(
            symbol=self._symbol,
            side=side_n,
            qty=qty_f,
            submit_enabled=place_attempted,
            reduce_only=reduce_only,
        )
        if intent is not None:
            record["intent"] = intent
        append_live_decision(self._data_root, record)
        if place_attempted:
            self._reconcile_with_venue(feed_ts=feed_ts)
        return record

    def _reconcile_with_venue(self, *, feed_ts: Any) -> None:
        """Require the venue position to equal the engine position after an order.

        A transport failure can still have filled (ambiguous outcome) and another
        owner can trade the same coin; either leaves the engine unable to manage
        the real exposure, which is a technical failure that must stop the daemon.
        """
        expected = self._position.qty
        reader = getattr(self._client, "venue_position", None)
        try:
            if not callable(reader):
                raise RuntimeError("live client cannot read the venue position")
            venue = float(reader(self._symbol))
        except Exception as exc:  # noqa: BLE001 — any read failure is technical
            message = f"venue position read after a live order failed: {exc}"
            self._record_reconciliation_failure(
                feed_ts=feed_ts, venue_qty=None, error=message
            )
            raise LiveReconciliationError(message) from exc
        if not math.isclose(venue, expected, rel_tol=1e-9, abs_tol=_RECONCILE_ABS_TOL):
            message = (
                f"venue position {venue!r} {self._symbol} does not match the engine "
                f"position {expected!r} after a live order (ambiguous fill or another "
                "owner trading this coin); stopping"
            )
            self._record_reconciliation_failure(
                feed_ts=feed_ts, venue_qty=venue, error=message
            )
            raise LiveReconciliationError(message)
        # Adopt the venue's exact lot-sized value: float residue from netting
        # (0.3 - 0.1 = 0.19999999999999998) would otherwise round a later
        # reduce-only close down one lot and strand that lot open.
        if venue == 0.0:
            self._position.qty = 0.0
            self._position.avg_px = 0.0
        else:
            self._position.qty = venue

    def _record_reconciliation_failure(
        self, *, feed_ts: Any, venue_qty: float | None, error: str
    ) -> None:
        logger.error("live reconciliation failed: %s", error)
        append_live_decision(
            self._data_root,
            {
                "execution_mode": "live",
                "network": NETWORK_MAINNET,
                "feed_ts": feed_ts,
                "run_id": self._run_id,
                "export_id": self._export_id,
                "strategy_name": self._strategy_name,
                "symbol": self._symbol,
                "timeframe": self._timeframe,
                "action": "venue_reconciliation_failed",
                "position_qty": self._position.qty,
                "venue_position_qty": venue_qty,
                "error": error,
                "submitted": False,
                "place_attempted": False,
                "live_phase": bool(self.place_enabled),
            },
        )

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
        if remaining <= _DUST_QTY and open_qty <= _DUST_QTY:
            pos.qty = 0.0
            pos.avg_px = 0.0
        elif remaining > _DUST_QTY:
            pos.qty = remaining if pos.qty > 0 else -remaining
        else:
            pos.qty = open_qty if signed > 0 else -open_qty
            pos.avg_px = fill_px
