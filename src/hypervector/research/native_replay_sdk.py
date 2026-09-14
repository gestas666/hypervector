"""Reusable signing-incapable native SDK replay with one exact shared account.

This boundary requires explicit market observations and execution books. It does
not infer trigger crossings, queue fills, liquidations or partial-close collateral.
Those events must be supplied by the replay scheduler and its declared scenario.
"""

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from hashlib import sha256

from hypervector.live.hyperliquid_perp_parsing import parse_book_for_symbol
from hypervector.live.perp_venue_identity import parse_perp_venue_identity
from hypervector.research.native_replay_account import (
    ExactFillAccount,
    REPLAY_DECIMAL_PRECISION,
    ReplayPosition,
)
from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_depth import RecordedBook
from hypervector.research.native_replay_events import (
    FillEvent,
    FundingEvent,
    require_amount,
    require_clock,
    require_name,
)
from hypervector.research.native_replay_receipts import AcceptedIoc, IocOrder, ReceiptTiming
from hypervector.research.native_replay_protective import ReplayProtectiveExecution
from hypervector.research.native_replay_sdk_exchange import ReplaySdkExchange
from hypervector.research.native_replay_sdk_info import ReplaySdkInfo
from hypervector.research.native_replay_sdk_models import (
    ReplayOrderRecord,
    ReplaySdkTiming,
    replay_market,
)
from hypervector.research.native_replay_timeline import ReplayRuntimeClock, ReplayTimeline
from hypervector.research.native_replay_unified import (
    IsolatedCollateral,
    MaintenanceTier,
    UnifiedAccountWire,
    project_unified_account,
)
from hypervector.research.native_replay_venue import RecordedIocVenue

__all__ = ["ReplaySdk", "ReplaySdkTiming"]
ExecutionBook = Callable[[str, int, Decimal], RecordedBook]
PartialCollateral = Callable[
    [ReplayPosition, ReplayPosition, IsolatedCollateral, tuple[FillEvent, ...]], IsolatedCollateral
]


class ReplaySdk:
    """Own shared offline Info/Exchange ports, clocks, receipts and exact economics."""

    def __init__(
        self,
        *,
        clock: ReplayClock,
        initial_cash: Decimal,
        symbols: tuple[str, ...],
        metadata_by_dex: Mapping[str, object],
        dexes: object,
        fees: object,
        maintenance: Mapping[str, tuple[MaintenanceTier, ...]],
        execution_book: ExecutionBook,
        timing: ReplaySdkTiming,
        decision_time: Callable[[str, bool], int],
        maximum_book_delay_ms: int = 0,
        partial_collateral: PartialCollateral | None = None,
    ) -> None:
        """Require explicit scenario sources; never load credentials or instantiate SDK clients."""
        require_clock(maximum_book_delay_ms, "maximum book delay")
        if set(maintenance) != set(symbols):
            raise ValueError("maintenance schedules must cover the exact replay universe")
        self.clock, self.symbols = clock, symbols
        self.account = ExactFillAccount(initial_cash, symbols)
        self.metadata_by_dex, self.dexes, self.fees = (
            deepcopy(dict(metadata_by_dex)),
            deepcopy(dexes),
            deepcopy(fees),
        )
        self.markets = {
            s: replay_market(
                s,
                self.metadata_by_dex[parse_perp_venue_identity(s).perp_dex],
                self.dexes,
                self.fees,
            )
            for s in symbols
        }
        self.maintenance = dict(maintenance)
        for tiers in self.maintenance.values():
            IsolatedCollateral(Decimal(0), tiers)
        self.execution_book, self.timing = execution_book, timing
        self.decision_time = decision_time
        self.maximum_book_delay_ms, self.partial_collateral = (
            maximum_book_delay_ms,
            partial_collateral,
        )
        self._initialize_records()
        self.venue = RecordedIocVenue(self.account, clock, oid_allocator=self.next_oid)
        self.info = ReplaySdkInfo(self)
        self.exchange = ReplaySdkExchange(self)
        self.protective = ReplayProtectiveExecution(self)

    def _initialize_records(self) -> None:
        self.mid_prices: dict[str, Decimal] = {}
        self._price_observations: dict[str, tuple[int, Decimal, Decimal | None]] = {}
        self.observed_books: dict[str, object] = {}
        self._book_observation_ms: dict[str, int] = {}
        self.collateral: dict[str, IsolatedCollateral] = {}
        self.leverage: dict[str, int] = {}
        self.orders: dict[int, ReplayOrderRecord] = {}
        self.fill_rows: list[tuple[int, dict[str, object]]] = []
        self.funding_rows: list[tuple[int, dict[str, object]]] = []
        self.response_losses: set[str] = set()
        self._funding_requests: dict[str, tuple[object, ...]] = {}
        self._pending_iocs: set[str] = set()
        self._next_order = 0
        self.timeline = ReplayTimeline(self.clock, self._advance_iocs)
        self.runtime_clock = ReplayRuntimeClock(self.timeline)

    def next_oid(self) -> int:
        """Allocate one namespace across market, stop and target orders."""
        self._next_order += 1
        return self._next_order

    def observe_prices(
        self, symbol: str, *, source_time_ms: int, mark: Decimal, mid: Decimal | None
    ) -> None:
        """Keep causal mark and midpoint fields distinct; neither is an oracle substitute."""
        require_clock(source_time_ms, "price observation time")
        require_amount(mark, "observed mark", positive=True)
        if mid is not None:
            require_amount(mid, "observed midpoint", positive=True)
        if symbol not in self.markets:
            raise ValueError(f"unknown replay market: {symbol}")
        current = (source_time_ms, mark, mid)
        prior = self._price_observations.get(symbol)
        if prior and (
            source_time_ms < prior[0] or (source_time_ms == prior[0] and current != prior)
        ):
            raise ValueError("regressing or conflicting replay price observation")
        if prior == current:
            return
        self.account.mark(
            self.clock.next_stamp(), source_time_ms=source_time_ms, prices={symbol: mark}
        )
        if mid is None:
            self.mid_prices.pop(symbol, None)
        else:
            self.mid_prices[symbol] = mid
        self._price_observations[symbol] = current

    def observed_mark(self, symbol: str, source_time_ms: int) -> Decimal:
        """Resolve the exact available mark observation cited by a modeled trigger event."""
        require_clock(source_time_ms, "mark observation time")
        current = self._price_observations.get(symbol)
        if current is None or current[0] != source_time_ms:
            raise ValueError("stop event requires the exact available mark observation")
        return current[1]

    def observe_book(self, symbol: str, payload: object) -> None:
        """Preserve the original native L2 payload, including real level order counts."""
        observed = parse_book_for_symbol(payload, symbol=symbol, depth_levels=20)
        if observed.exchange_timestamp_ms > self.clock.now_ms:
            raise ValueError("observed replay book cannot come from the future")
        if symbol not in self.markets:
            raise ValueError(f"unknown replay market: {symbol}")
        prior = self._book_observation_ms.get(symbol)
        if prior is not None and (
            observed.exchange_timestamp_ms < prior
            or (observed.exchange_timestamp_ms == prior and payload != self.observed_books[symbol])
        ):
            raise ValueError("regressing or conflicting replay book observation")
        self.observed_books[symbol] = deepcopy(payload)
        self._book_observation_ms[symbol] = observed.exchange_timestamp_ms

    def account_wire(self) -> UnifiedAccountWire:
        """Project only causal economic mutations and explicitly modeled isolated collateral."""
        self.advance_to(self.clock.now_ms)
        view = self.account.snapshot()
        return project_unified_account(
            view,
            symbols=self.symbols,
            marks={symbol: view.mark_prices[symbol] for symbol in view.positions},
            collateral=self.collateral,
            additional_hold_usd=Decimal(0),
            observed_time_ms=self.clock.now_ms,
        )

    def advance_to(self, time_ms: int) -> None:
        """Process intermediate market/settlement events before returning from native waits."""
        self.timeline.advance_to(time_ms)

    def schedule(self, time_ms: int, identity: str, apply: Callable[["ReplaySdk"], None]) -> None:
        """Register explicit causal source events; callbacks must not advance clocks themselves."""
        self.timeline.schedule(time_ms, identity, lambda: apply(self))

    def _advance_iocs(self, time_ms: int) -> None:
        self.venue.advance_to(time_ms)
        for identity in tuple(self._pending_iocs):
            execution = self.venue.execution(identity)
            if execution.applied:
                self._publish_ioc(execution)
                self._pending_iocs.remove(identity)

    def submit_ioc(self, order: IocOrder, book: RecordedBook, timing: ReceiptTiming) -> object:
        """Bind an actual native submitted quantity to the exact finite-depth account venue."""
        if any(row.client_id == order.client_order_id for row in self.orders.values()):
            raise ValueError("replay SDK client order identity was already submitted")
        self.venue.submit(order, book, timing, maximum_book_delay_ms=self.maximum_book_delay_ms)
        execution = self.venue.execution(order.client_order_id)
        self._pending_iocs.add(order.client_order_id)
        self.orders[execution.oid] = ReplayOrderRecord(
            execution.oid,
            order.client_order_id,
            order.symbol,
            order.side == "buy",
            order.quantity,
            order.quantity,
            order.limit_price,
            None,
            order.reduce_only,
            False,
            order.dispatch_time_ms,
            timing.order_visible_ms,
            "pending",
            order.dispatch_time_ms,
            timing.order_visible_ms,
        )
        self.advance_to(timing.response_ms)
        return self.venue.response(order.client_order_id)

    def _publish_ioc(self, execution: AcceptedIoc) -> None:
        before = execution.position_before
        match = execution.completed_match
        self.orders[execution.oid] = replace(
            self.orders[execution.oid],
            previous=self.orders[execution.oid],
            remaining=match.unfilled_quantity,
            status="filled" if match.disposition == "complete" else "canceled",
            status_ms=execution.book.exchange_time_ms,
        )
        if not execution.fills:
            return
        self.update_fill_collateral(
            execution.order.symbol, before, execution.position_after, execution.fills
        )
        for fill in execution.fills:
            gross = (
                Decimal(0)
                if not fill.reduce_only
                else (
                    fill.quantity
                    * (fill.price - before.entry_price)
                    * (1 if before.quantity_signed > 0 else -1)
                )
            )
            self.record_fill(
                fill,
                gross=gross,
                client_id=execution.order.client_order_id,
                visible_ms=execution.timing.fill_visible_ms,
                crossed=True,
            )

    def update_fill_collateral(
        self,
        name: str,
        before: ReplayPosition | None,
        after: ReplayPosition | None,
        fills: tuple[FillEvent, ...],
    ) -> None:
        """Apply the declared collateral model to the positions at this exact execution."""
        if after is None:
            del self.collateral[name]
        elif before is None:
            fees = sum((fill.fee_usd for fill in fills), Decimal(0))
            self.collateral[name] = IsolatedCollateral(
                after.allocated_initial_margin_usd - fees, self.maintenance[name]
            )
        elif self.partial_collateral is None:
            raise ValueError(f"partial {name} close requires an explicit collateral scenario")
        else:
            self.collateral[name] = self.partial_collateral(
                before, after, self.collateral[name], fills
            )

    def record_fill(
        self, fill: FillEvent, *, gross: Decimal, client_id: str, visible_ms: int, crossed: bool
    ) -> None:
        """Expose exact quantities, signed fees and gross close PnL in native wire format."""
        direction = "Long" if (fill.side == "buy") != fill.reduce_only else "Short"
        row = {
            "coin": fill.symbol,
            "oid": int(fill.order_id),
            "tid": len(self.fill_rows) + 1,
            "px": str(fill.price),
            "sz": str(fill.quantity),
            "side": "B" if fill.side == "buy" else "A",
            "time": fill.fill_time_ms,
            "fee": str(fill.fee_usd),
            "feeToken": "USDC",
            "closedPnl": str(gross),
            "crossed": crossed,
            "dir": f"{'Close' if fill.reduce_only else 'Open'} {direction}",
            "hash": "0x" + sha256(fill.fill_id.encode()).hexdigest(),
            "cloid": client_id,
        }
        self.fill_rows.append((visible_ms, row))

    def settle_funding(
        self,
        event_id: str,
        symbol: str,
        *,
        rate: Decimal,
        oracle_price: Decimal,
        effective_time_ms: int,
        visible_delay_ms: int,
    ) -> None:
        """Settle signed size times explicit oracle price and rate at the economic event clock."""
        require_name(event_id, "funding ID")
        require_clock(effective_time_ms, "funding event time")
        request = (symbol, rate, oracle_price, effective_time_ms, visible_delay_ms)
        if event_id in self._funding_requests:
            if self._funding_requests[event_id] != request:
                raise ValueError("conflicting replay funding identity")
            return
        require_amount(rate, "funding rate")
        require_amount(oracle_price, "funding oracle price", positive=True)
        require_clock(visible_delay_ms, "funding visibility delay")
        if effective_time_ms != self.clock.now_ms or symbol not in self.markets:
            raise ValueError("funding requires its exact economic clock and a configured symbol")
        position = self.account.snapshot().positions.get(symbol)
        if position is not None:
            self._fund_position(event_id, position, rate, oracle_price, visible_delay_ms)
        self._funding_requests[event_id] = request

    def _fund_position(
        self,
        event_id: str,
        position: ReplayPosition,
        rate: Decimal,
        oracle_price: Decimal,
        visible_delay_ms: int,
    ) -> None:
        with localcontext() as context:
            context.prec = REPLAY_DECIMAL_PRECISION
            amount = -position.quantity_signed * oracle_price * rate
            old = self.collateral[position.symbol]
            collateral = replace(old, cash_usd=old.cash_usd + amount)
            self.account.apply_funding(
                FundingEvent(
                    event_id, position.symbol, amount, self.clock.now_ms, self.clock.next_stamp()
                )
            )
        self.collateral[position.symbol] = collateral
        self.funding_rows.append(
            (
                self.clock.now_ms + visible_delay_ms,
                {
                    "time": self.clock.now_ms,
                    "hash": "0x" + sha256(event_id.encode()).hexdigest(),
                    "delta": {
                        "type": "funding",
                        "coin": position.symbol,
                        "usdc": str(amount),
                        "szi": str(position.quantity_signed),
                        "fundingRate": str(rate),
                    },
                },
            )
        )
