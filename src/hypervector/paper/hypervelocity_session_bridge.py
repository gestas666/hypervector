"""Ledger bridge between event shadow execution and the paper portfolio engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent, StreamGap
from hypervector.execution import OrderCommand, VenueOrderEvent
from hypervector.paper.book import BookFeed
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
    ShadowCycle,
)
from hypervector.paper.hypervelocity_order_telemetry import (
    fill_metadata,
    order_action,
    order_metadata,
    timestamp,
)
from hypervector.paper.hypervelocity_market_projection import book_snapshot_from_event
from hypervector.paper.ledger import append_paper_decision
from hypervector.paper.liquidation_execution import LiquidationExactMarkFillModel
from hypervector.paper.maker_execution import PendingMakerEntry, PostOnlyLimitFillModel
from hypervector.paper.maximum_hold_execution import (
    FreshBboTakerFillModel,
    maximum_hold_order_intent,
)
from hypervector.paper.peak_observer_telemetry import (
    PeakObserverLedgerIdentity,
    PeakObserverTelemetryBridge,
)
from hypervector.paper.peak_protection_observer import PeakProtectionObserver
from hypervector.paper.shadow_execution_models import (
    ShadowExecutionRecord,
    ShadowLiquidation,
)
from hypervector.strategies.hypervelocity_runtime import RuntimeMarketState


@dataclass(frozen=True)
class ShadowLedgerContext:
    """Stable identity attached to every event-shadow ledger row."""

    run_id: str
    export_id: str
    strategy_name: str
    symbol: str
    timeframe: str


@dataclass(frozen=True)
class ShadowOrderAnnotation:
    """Report-only model context that cannot alter an order command."""

    conviction: float
    conviction_source: str
    metalabel_p: float | None
    metalabel_bundle_id: str | None


class HypervelocitySessionBridge:
    """Apply controller cycles once to portfolio state and the durable ledger."""

    def __init__(
        self,
        *,
        controller: HypervelocityShadowController,
        engine: ExplicitFillEngine,
        data_root: Path,
        book_feed: BookFeed,
        context: ShadowLedgerContext,
        peak_observer: PeakProtectionObserver | None = None,
    ) -> None:
        self._controller = controller
        self._engine = engine
        self._root = data_root
        self._book_feed = book_feed
        self._context = context
        self._peak_telemetry = (
            PeakObserverTelemetryBridge(
                observer=peak_observer,
                data_root=data_root,
                identity=PeakObserverLedgerIdentity(
                    run_id=context.run_id,
                    export_id=context.export_id,
                    strategy_name=context.strategy_name,
                    symbol=context.symbol,
                    timeframe=context.timeframe,
                ),
            )
            if peak_observer is not None
            else None
        )
        self._last_fill_count = 0
        self._order_annotations: dict[str, ShadowOrderAnnotation] = {}
        self._last_annotation: str | None = None

    @property
    def controller(self) -> HypervelocityShadowController:
        """Return the backend-authoritative event controller."""
        return self._controller

    @property
    def pending_maker_entry(self) -> PendingMakerEntry | None:
        """Project coordinator pending state into existing backend telemetry."""
        pending = self._controller.state.pending_entry
        if pending is None:
            return None
        command = pending.command
        if command.limit_price is None:
            raise RuntimeError("pending limit entry has no limit price")
        return PendingMakerEntry(
            direction="long" if command.side == "buy" else "short",
            qty=command.quantity - pending.cumulative_quantity,
            limit_price=command.limit_price,
            submitted_at=timestamp(command.submitted_at),
        )

    @property
    def last_fill_count(self) -> int:
        """Return the exact fill-event count from the latest controller cycle."""
        return self._last_fill_count

    @property
    def liquidation_price(self) -> float | None:
        """Return the backend-authoritative isolated liquidation boundary."""
        return self._controller.port.liquidation_price

    @property
    def active_target_prices(self) -> tuple[float, ...]:
        """Return prices for remaining backend target orders."""
        prices = [
            float(target.command.limit_price)
            for target in self._controller.state.active_targets
            if target.command.limit_price is not None
            and target.cumulative_quantity < target.command.quantity
        ]
        return tuple(dict.fromkeys(prices))

    def on_market(
        self,
        market: RuntimeMarketState,
        *,
        annotation: ShadowOrderAnnotation | None = None,
    ) -> str | None:
        """Route one classified market state and ledger its order effects."""
        cycle = self._controller.on_market(market)
        if annotation is not None:
            for command in cycle.commands:
                if command.order_role == "entry":
                    self._order_annotations[command.client_order_id] = annotation
        return self._apply_cycle(cycle)

    def seed_order_annotation(
        self,
        client_order_id: str,
        annotation: ShadowOrderAnnotation,
    ) -> None:
        """Restore report-only context for a durable open order."""
        self._controller.command_for(client_order_id)
        self._order_annotations[client_order_id] = annotation

    def ingest(
        self,
        event: L2SnapshotEvent | PublicTradeEvent | StreamGap,
    ) -> str | None:
        """Route one public event, update L2 telemetry, and ledger order effects."""
        if isinstance(event, L2SnapshotEvent):
            self._book_feed.update(book_snapshot_from_event(event))
        return self._apply_cycle(self._controller.ingest(event))

    def apply_funding(
        self,
        *,
        hourly_rate: float,
        oracle_price: float,
        applied_at: str,
    ) -> None:
        """Apply one hourly transfer identically to venue and ledger accounts."""
        signed_net = self._controller.port.apply_funding(
            hourly_rate=hourly_rate,
            mark_price=oracle_price,
            applied_at=applied_at,
        )
        record = self._engine.apply_funding(
            feed_ts=applied_at,
            oracle_px=oracle_price,
            funding_rate_hourly=hourly_rate,
            record_metadata={
                "execution_model": "nautilus_event_v1",
                "execution_data_source": "live_meta_and_asset_contexts",
                "execution_evidence_fresh": self._controller.port.evidence_fresh,
                "margin_model": "hyperliquid_isolated_v1",
                "liquidation_price": self.liquidation_price,
            },
        )
        if record is None:
            if signed_net != 0.0:
                raise RuntimeError("flat ledger received non-zero shadow funding")
            return
        payment = float(record["funding_payment_usd"])
        if not math.isclose(payment, -signed_net, abs_tol=1e-10):
            raise RuntimeError("event shadow funding differs from ledger funding")

    def apply_mark(self, *, mark_price: float, observed_at: str) -> str | None:
        """Reconcile a mark-price isolated liquidation across both state stores."""
        self._observe_peak(mark_price=mark_price, observed_at=observed_at)
        before = self._engine.position.qty
        liquidated = self._controller.port.mark(
            mark_price=mark_price,
            observed_at=observed_at,
        )
        if not liquidated:
            return None
        if before == 0.0:
            raise RuntimeError("shadow port liquidated while ledger was flat")
        liquidation = self._controller.port.last_liquidation
        if liquidation is None:
            raise RuntimeError("liquidation state disappeared before ledger write")
        action = _liquidation_action(liquidation)
        self._engine.apply_market_fill(
            feed_ts=observed_at,
            action=action,
            side="sell" if before > 0.0 else "buy",
            qty=liquidation.filled_quantity,
            mark_px=liquidation.execution_price,
            fill_model=LiquidationExactMarkFillModel(),
            fee_override_usd=liquidation.execution_fee_usd,
            exit_reason="isolated_mark_liquidation",
            record_metadata=_liquidation_metadata(
                liquidation,
                evidence_fresh=self._controller.port.evidence_fresh,
            ),
        )
        cycle = self._controller.reconcile_liquidation(observed_at)
        self._apply_cycle(cycle)
        self.sync_peak_observer(
            observed_at=observed_at,
            coverage_complete_since_entry=True,
        )
        return action

    def sync_peak_observer(
        self,
        *,
        observed_at: str,
        coverage_complete_since_entry: bool,
    ) -> None:
        """Mirror actual position state into report-only observer telemetry."""
        telemetry = self._peak_telemetry
        if telemetry is None:
            return
        position = self._engine.position
        telemetry.sync_position(
            quantity=position.qty,
            average_price=position.avg_px if position.qty != 0.0 else None,
            observed_at=observed_at,
            coverage_complete_since_entry=coverage_complete_since_entry,
        )

    def _apply_cycle(self, cycle: ShadowCycle) -> str | None:
        self._inherit_target_annotations(cycle)
        records = {
            (record.event.client_order_id, record.event.cumulative_quantity): record
            for record in cycle.execution_records
        }
        last_action: str | None = None
        fill_count = 0
        for event in cycle.venue_events:
            command = self._controller.command_for(event.client_order_id)
            if event.event_type in {"partially_filled", "filled"}:
                record = records.get((event.client_order_id, event.cumulative_quantity))
                if record is None:
                    raise RuntimeError(
                        "normalized fill has no execution evidence record"
                    )
                last_action = self._apply_fill(command, event, record)
                fill_count += 1
            else:
                self._record_order_event(command, event)
        annotations, self._last_annotation = _new_annotations(
            self._last_annotation,
            cycle.annotations,
        )
        for annotation in annotations:
            self._record_annotation(annotation)
        self._validate_position_parity()
        self._last_fill_count = fill_count
        return last_action

    def _inherit_target_annotations(self, cycle: ShadowCycle) -> None:
        inherited = next(
            (
                self._order_annotations[event.client_order_id]
                for event in cycle.venue_events
                if event.client_order_id in self._order_annotations
            ),
            None,
        )
        if inherited is None:
            return
        for command in cycle.commands:
            if command.order_role in {"target", "exit"}:
                self._order_annotations[command.client_order_id] = inherited

    def _apply_fill(
        self,
        command: OrderCommand,
        event: VenueOrderEvent,
        evidence: ShadowExecutionRecord,
    ) -> str:
        if event.fill_price is None:
            raise RuntimeError("normalized fill has no price")
        before = abs(self._engine.position.qty)
        if command.order_role == "entry":
            action = "enter_long" if command.side == "buy" else "enter_short"
        else:
            action = (
                "close" if event.last_quantity >= before - 1e-12 else "reduce_target"
            )
        maximum_hold_exit = command.order_role == "exit"
        self._engine.apply_market_fill(
            feed_ts=event.event_at,
            action=action,
            side=command.side,
            qty=event.last_quantity,
            mark_px=event.fill_price,
            order_intent_override=(
                maximum_hold_order_intent(command, event) if maximum_hold_exit else None
            ),
            fill_model=(
                FreshBboTakerFillModel()
                if maximum_hold_exit
                else PostOnlyLimitFillModel()
            ),
            fee_override_usd=event.fee_usd,
            exit_reason=(
                "maximum_hold_24h"
                if maximum_hold_exit
                else "take_profit_8pct_margin"
                if action == "close"
                else None
            ),
            record_metadata=fill_metadata(
                event,
                evidence,
                liquidation_price=self.liquidation_price,
            ),
            **self._annotation_kwargs(command.client_order_id),
        )
        self.sync_peak_observer(
            observed_at=event.event_at,
            coverage_complete_since_entry=True,
        )
        return action

    def _observe_peak(self, *, mark_price: float, observed_at: str) -> None:
        telemetry = self._peak_telemetry
        if telemetry is None:
            return
        telemetry.observe_mark(
            mark_price=mark_price,
            observed_at=observed_at,
            book=self._book_feed.latest(),
            evidence_fresh=self._controller.port.evidence_fresh_at(observed_at),
        )

    def _record_order_event(
        self,
        command: OrderCommand,
        event: VenueOrderEvent,
    ) -> None:
        if command.limit_price is None:
            raise RuntimeError("event-shadow order has no limit price")
        self._engine.record_order_event(
            feed_ts=event.event_at,
            action=order_action(command, event),
            side=command.side,
            qty=command.quantity,
            limit_px=command.limit_price,
            status=event.event_type,
            reason=event.reason,
            record_metadata=order_metadata(
                event,
                self._controller.port.order_telemetry(event.client_order_id),
                liquidation_price=self.liquidation_price,
            ),
            **self._annotation_kwargs(command.client_order_id),
        )

    def _annotation_kwargs(self, client_order_id: str) -> dict[str, object]:
        annotation = self._order_annotations.get(client_order_id)
        if annotation is None:
            return {}
        return {
            "conviction": annotation.conviction,
            "conviction_source": annotation.conviction_source,
            "metalabel_p": annotation.metalabel_p,
            "metalabel_bundle_id": annotation.metalabel_bundle_id,
        }

    def _record_annotation(self, annotation: str) -> None:
        position = self._engine.position
        account = self._controller.port.account_snapshot()
        realized_equity = self._engine.initial_cash + position.realized_pnl
        append_paper_decision(
            self._root,
            {
                "feed_ts": account.observed_at,
                "run_id": self._context.run_id,
                "export_id": self._context.export_id,
                "strategy_name": self._context.strategy_name,
                "symbol": self._context.symbol,
                "timeframe": self._context.timeframe,
                "action": annotation,
                "execution_model": "nautilus_event_v1",
                "execution_mode": "shadow",
                "submitted": False,
                "place_attempted": False,
                "position_qty": position.qty,
                "position_avg_px": position.avg_px,
                "liquidation_price": self.liquidation_price,
                "realized_pnl": position.realized_pnl,
                "unrealized_pnl": account.equity_usd - realized_equity,
                "equity": account.equity_usd,
                "init_cash": self._engine.initial_cash,
            },
        )

    def _validate_position_parity(self) -> None:
        expected = self._controller.state.position_quantity
        if self._controller.state.position_direction == "short":
            expected = -expected
        actual = self._engine.position.qty
        if not math.isclose(actual, expected, abs_tol=1e-10):
            raise RuntimeError(
                f"event shadow position mismatch ledger={actual} runtime={expected}"
            )


def _new_annotations(
    previous: str | None,
    annotations: tuple[str, ...],
) -> tuple[tuple[str, ...], str | None]:
    """Return annotation state changes and the latest active annotation."""
    if not annotations:
        return (), None
    emitted: list[str] = []
    latest = previous
    for annotation in annotations:
        if annotation != latest:
            emitted.append(annotation)
        latest = annotation
    return tuple(emitted), latest


def _liquidation_action(liquidation: ShadowLiquidation) -> str:
    if liquidation.method == "backstop":
        return "backstop_liquidation"
    if liquidation.remaining_quantity > 1e-12:
        return "partial_liquidation"
    return "liquidation"


def _liquidation_metadata(
    liquidation: ShadowLiquidation,
    *,
    evidence_fresh: bool,
) -> dict[str, object]:
    return {
        "venue_event_type": "liquidated",
        "execution_model": "nautilus_event_v1",
        "execution_data_source": "hyperliquid_mark",
        "execution_evidence_fresh": evidence_fresh,
        "liquidity_side": "taker",
        "margin_model": "hyperliquid_isolated_v1",
        "liquidation_price": liquidation.boundary_price,
        "liquidation_trigger_mark": liquidation.mark_price,
        "liquidation_isolated_margin_usd": liquidation.isolated_margin_usd,
        "liquidation_position_equity_usd": liquidation.position_equity_usd,
        "liquidation_maintenance_margin_usd": (liquidation.maintenance_margin_usd),
        "clearance_fee_usd": liquidation.clearance_fee_usd,
        "liquidation_execution_model": liquidation.execution_model,
        "liquidation_method": liquidation.method,
        "liquidation_attempted_qty": liquidation.attempted_quantity,
        "liquidation_filled_qty": liquidation.filled_quantity,
        "liquidation_remaining_qty": liquidation.remaining_quantity,
        "liquidation_partial_rule_applied": liquidation.partial_rule_applied,
        "liquidation_cooldown_until_ms": liquidation.cooldown_until_ms,
        "liquidation_market_filled_qty": liquidation.market_filled_quantity,
        "liquidation_backstop_qty": liquidation.backstop_quantity,
    }
