"""Scheduled synthetic SDK ports around the actual engines and exact IOC venue.

Receipt delays, books, partial terminal status and collateral are explicit
scenario inputs, not native partial-close collateral evidence. Internal
IOC fills supply economic truth; SDK readers expose only their scheduled subset.
"""

from dataclasses import dataclass, replace
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from types import SimpleNamespace

from hyperliquid.exchange import Exchange
from hyperliquid.utils.types import Cloid
from native_replay_engine_fixture import FEE_RATE, SIZE_DECIMALS, EngineReplayFixture
from requests import RequestException

from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.multi_asset_live_config import AssetLiveConfig
from hypervector.live.asset_state import AssetLiveSnapshot, AssetLiveState
from hypervector.research.native_replay_account import ReplayPosition
from hypervector.research.native_replay_depth import ExactLevel, RecordedBook
from hypervector.research.native_replay_unified import (
    IsolatedCollateral,
    MaintenanceTier,
)
from hypervector.research.native_replay_venue import (
    IocOrder,
    ReceiptTiming,
    RecordedIocVenue,
)

D = Decimal
IOC_FILL_DELAY_MS = 100
IOC_RESPONSE_DELAY_MS = 200
FILL_HISTORY_DELAY_MS = 300
ORDER_STATUS_DELAY_MS = 400
PROTECTION_RESPONSE_DELAY_MS = 50
PROTECTION_VISIBLE_DELAY_MS = 350


@dataclass
class ScheduledOrder:
    """An exact synthetic order identity with independent status visibility."""

    wire: dict[str, object]
    status: str
    status_time_ms: int
    visible_at_ms: int
    rested: bool = False


class ScheduledEngineFixture(EngineReplayFixture):
    """Run real engine recovery with scheduled IOC and protective-order receipts."""

    def __init__(
        self,
        root: Path,
        *,
        lost: str | None,
        recovery_delay_ms: int | None = None,
        partial_operation: str | None = None,
        partial_status: str = "filled",
    ) -> None:
        """Share one exact account and clock without constructing venue clients."""
        if partial_operation not in {None, "entry", "close"}:
            raise ValueError("partial operation must be entry, close or absent")
        if partial_status not in {"filled", "canceled"}:
            raise ValueError("partial terminal status must be filled or canceled")
        super().__init__(root, partial_entry=False, initial_cash=D(5000))
        self.lost = lost
        self.recovery_delay_ms = recovery_delay_ms
        self.partial_operation = partial_operation
        self.partial_status = partial_status
        self.partial_close_collateral: dict[str, IsolatedCollateral] = {}
        self.venue = RecordedIocVenue(self.account, self.clock)
        self.scheduled: dict[int, ScheduledOrder] = {}
        self.order_visible_at: dict[int, int] = {}
        self.fill_visible_at: dict[int, int] = {}
        self.ioc_oid_map: dict[int, int] = {}
        self.ioc_requests: list[IocOrder] = []
        self._info.query_order_by_oid.side_effect = self._query_order
        self._info.frontend_open_orders.side_effect = self._visible_orders
        self._info.user_fills.side_effect = self._visible_fills

    def enter_current(self, asset: AssetLiveConfig, *, last_side: bool = False) -> AssetLiveSnapshot:
        """Drive the configured provider plan and sizing through the actual engine."""
        symbol = asset.symbol
        provider = next(p for p in self.config.providers if symbol in p.execution_symbols)
        sides = sorted(provider.executable_sides(symbol))
        side = sides[-1] if last_side else sides[0]
        engine = self.engine(asset)
        self.engines[symbol] = engine
        assert engine.start().state is AssetLiveState.FLAT
        decision = self.clock.now_ms
        self.prepare_entry(symbol, side, decision)
        plan = provider.execution_for(symbol, side).bind(
            strategy_id=provider.strategy_id,
            stop_anchor=98 if side == "long" else 102,
        )
        engine.record_strategy_decision(
            {"execution_plan": plan.as_payload(), "decision_time_ms": decision}
        )
        result = engine.enter(
            side=side,
            mark_price=100,
            decision_time_ms=decision,
            entry_sizing=provider.entry_sizing(symbol, side),
            entry_deadline=EntrySubmissionDeadline(decision, 30000, lambda: self.clock.now_ms),
        )
        assert result.execution_plan == plan
        return result

    def _delay(self, operation: str, default_ms: int) -> int:
        return (
            self.recovery_delay_ms
            if self.lost == operation and self.recovery_delay_ms is not None
            else default_ms
        )

    def _visible_orders(self, address: str, dex: str) -> list[dict[str, object]]:
        return [
            dict(row.wire)
            for row in self.scheduled.values()
            if row.rested
            and (
                (row.status == "open" and self.clock.now_ms >= row.visible_at_ms)
                or (row.status == "canceled" and self.clock.now_ms < row.visible_at_ms)
            )
        ]

    def _visible_fills(self, address: str) -> list[dict[str, object]]:
        return [
            dict(row) for row in self.fills if self.fill_visible_at[row["tid"]] <= self.clock.now_ms
        ]

    def _query_order(self, address: str, identity: int | str) -> dict[str, object]:
        matches = [
            row
            for oid, row in self.scheduled.items()
            if oid == identity or row.wire["cloid"] == str(identity)
        ]
        assert len(matches) <= 1
        if not matches or self.clock.now_ms < matches[0].visible_at_ms:
            return {"status": "unknownOid"}
        row = matches[0]
        return {
            "status": "order",
            "order": {
                "order": dict(row.wire),
                "status": row.status,
                "statusTimestamp": row.status_time_ms,
            },
        }

    def _open(
        self, name: str, is_buy: bool, sz: float, *, px: float, slippage: float, cloid: Cloid
    ) -> object:
        self.entry_requests.append((name, D(str(sz))))
        return self._ioc(name, is_buy, sz, px, slippage, cloid, False)

    def _close(self, name: str, *, sz: float, px: float, slippage: float, cloid: Cloid) -> object:
        position = self.account.snapshot().positions[name]
        self.close_requests.append(
            {
                "stop_present": any(
                    row["coin"] == name and row["isTrigger"] for row in self.orders.values()
                ),
                "target_present": any(
                    row["coin"] == name and not row["isTrigger"] for row in self.orders.values()
                ),
            }
        )
        return self._ioc(name, position.quantity_signed < 0, sz, px, slippage, cloid, True)

    def _ioc(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float,
        slippage: float,
        cloid: Cloid,
        reduce: bool,
    ) -> object:
        now, quantity = self.clock.now_ms, D(str(sz))
        order = IocOrder(
            cloid.to_raw(),
            name,
            "buy" if is_buy else "sell",
            quantity,
            self._limit(name, is_buy, px, slippage),
            D(str(self.assets[name].leverage)),
            FEE_RATE,
            self.decisions[name],
            now,
            now + IOC_FILL_DELAY_MS,
            reduce,
        )
        delay = self._delay("close" if reduce else "entry", ORDER_STATUS_DELAY_MS)
        timing = ReceiptTiming(
            now + FILL_HISTORY_DELAY_MS,
            now + delay,
            now + IOC_RESPONSE_DELAY_MS,
            self.lost == ("close" if reduce else "entry"),
        )
        before = self.account.snapshot()
        self.venue.submit(order, self._book(order), timing, maximum_book_delay_ms=0)
        self.ioc_requests.append(order)
        self.venue.advance_to(timing.response_ms)
        self._publish_ioc(order, timing, before.positions.get(name))
        response = self.venue.response(order.client_order_id)
        assert response is not None
        oid = self.ioc_oid_map[self.venue._orders[order.client_order_id].oid]
        row = self.venue._orders[order.client_order_id]
        return self._ack(
            {
                "filled": {
                    "oid": oid,
                    "totalSz": str(row.match.filled_quantity),
                    "avgPx": str(row.match.vwap),
                }
            }
        )

    def _book(self, order: IocOrder) -> RecordedBook:
        step = D(1).scaleb(-SIZE_DECIMALS[order.symbol])
        operation = "close" if order.reduce_only else "entry"
        available = order.quantity
        if self.partial_operation == operation:
            available = (available / 2).quantize(step, rounding=ROUND_DOWN)
        first = (available / 2).quantize(step, rounding=ROUND_DOWN)
        assert first > 0
        return RecordedBook(
            f"synthetic:{order.client_order_id}",
            order.symbol,
            order.arrival_time_ms,
            step,
            (ExactLevel(D("99.9"), first), ExactLevel(D("99.8"), available - first)),
            (ExactLevel(D("100.1"), first), ExactLevel(D("100.2"), available - first)),
        )

    @staticmethod
    def _limit(name: str, is_buy: bool, price: float, slippage: float) -> Decimal:
        asset_id = 110000 if ":" in name else 0
        context = SimpleNamespace(
            info=SimpleNamespace(
                name_to_coin={name: name},
                coin_to_asset={name: asset_id},
                asset_to_sz_decimals={asset_id: SIZE_DECIMALS[name]},
            )
        )
        return D(str(Exchange._slippage_price(context, name, is_buy, slippage, price)))

    def _publish_ioc(
        self, order: IocOrder, timing: ReceiptTiming, before: ReplayPosition | None
    ) -> None:
        row, oid = self.venue._orders[order.client_order_id], self._next_oid()
        assert row.match.disposition in {"complete", "partial"}
        self.ioc_oid_map[row.oid] = oid
        self._collateral(
            order.symbol, sum((fill.fee_usd for fill in row.fills), D(0)), order.reduce_only
        )
        for fill in row.fills:
            gross = D(0)
            if order.reduce_only:
                assert before is not None
                gross = (
                    (fill.price - before.entry_price)
                    * fill.quantity
                    * (1 if before.quantity_signed > 0 else -1)
                )
            self._record_fill(replace(fill, order_id=str(oid)), gross, order.client_order_id)
            tid = len(self.fills)
            self.fills[-1]["tid"] = tid
            self.fill_visible_at[tid] = timing.fill_visible_ms
        status = self.partial_status if row.match.disposition == "partial" else "filled"
        wire = {
            "coin": order.symbol,
            "oid": oid,
            "sz": str(row.match.unfilled_quantity) if status == "canceled" else "0.0",
            "origSz": str(order.quantity),
            "cloid": order.client_order_id,
        }
        self.scheduled[oid] = ScheduledOrder(
            wire, status, row.book.exchange_time_ms, timing.order_visible_ms
        )
        self.order_visible_at[oid] = timing.order_visible_ms
        self.mutations.append("close" if order.reduce_only else "entry")

    def _collateral(self, name: str, fee: Decimal, reduce: bool) -> None:
        positions = self.account.snapshot().positions
        if reduce:
            if name in positions:
                assert name in self.partial_close_collateral, (
                    "partial close requires explicit scenario collateral; native transfer is unqualified"
                )
                self.collateral[name] = self.partial_close_collateral.pop(name)
            else:
                del self.collateral[name]
        else:
            rate = D("0.5") / D(str(self.assets[name].venue_max_leverage))
            self.collateral[name] = IsolatedCollateral(
                positions[name].allocated_initial_margin_usd - fee,
                (MaintenanceTier(D(0), rate, D(0)),),
            )

    def _stop(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        *,
        order_type: object,
        reduce_only: bool,
        cloid: object,
    ) -> object:
        now = self.clock.now_ms
        response = super()._stop(
            name, is_buy, sz, limit_px, order_type=order_type, reduce_only=reduce_only, cloid=cloid
        )
        oid = self._oid
        operation = "stop" if self.orders[oid]["isTrigger"] else "target"
        visible = now + self._delay(operation, PROTECTION_VISIBLE_DELAY_MS)
        self.scheduled[oid] = ScheduledOrder(
            dict(self.orders[oid]), "open", now, visible, rested=True
        )
        self.order_visible_at[oid] = visible
        self.clock.advance_to(now + PROTECTION_RESPONSE_DELAY_MS)
        if self.lost == operation:
            raise RequestException(f"synthetic {operation} response lost after acceptance")
        return response

    def _cancel(self, name: str, oid: int) -> object:
        now = self.clock.now_ms
        response = super()._cancel(name, oid)
        row = self.scheduled[oid]
        row.status, row.status_time_ms = "canceled", now
        row.visible_at_ms = now + self._delay("cancel", ORDER_STATUS_DELAY_MS)
        self.order_visible_at[oid] = row.visible_at_ms
        self.clock.advance_to(now + PROTECTION_RESPONSE_DELAY_MS)
        if self.lost == "cancel":
            raise RequestException("synthetic cancel response lost after cancellation")
        return response
