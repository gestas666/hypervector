"""Explicit paper fills: bar_close_slippage_v1 + funding rows.

Pure position math + decision append. No live orders, no sandbox client.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hypervector.paper.costs import CostProvider, CostSnapshot, funding_payment
from hypervector.paper.ledger import append_paper_decision

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
        self._position = PaperPosition()

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
        slip = float(snap.slippage_bps) / 10_000.0
        if side_n == "buy":
            fill_px = mark * (1.0 + slip)
        else:
            fill_px = mark * (1.0 - slip)

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
    ) -> dict:
        return {
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
            "fill_model_id": snap.fill_model_id,
            "slippage_bps": snap.slippage_bps,
            "taker_fee": snap.taker_fee,
            "maker_fee": snap.maker_fee,
            "fee_usd": fee_usd,
            "funding_rate_hourly": snap.funding_rate_hourly,
            "funding_payment_usd": funding_payment_usd,
            "costs_source": _costs_source(snap),
            "sandbox_enabled": self._sandbox_enabled,
            "conviction": self._conviction,
            "position_qty": self._position.qty,
            "position_avg_px": self._position.avg_px,
            "realized_pnl": self._position.realized_pnl,
        }

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
