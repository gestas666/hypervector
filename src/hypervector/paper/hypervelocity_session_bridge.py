"""Ledger bridge between event shadow execution and the paper portfolio engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent, StreamGap
from hypervector.execution import OrderCommand, VenueOrderEvent
from hypervector.paper.book import BookFeed, BookLevel, BookSnapshot
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
    ShadowCycle,
)
from hypervector.paper.ledger import append_paper_decision
from hypervector.paper.liquidation_execution import LiquidationExactMarkFillModel
from hypervector.paper.maker_execution import PendingMakerEntry, PostOnlyLimitFillModel
from hypervector.paper.shadow_execution_models import (
    ShadowExecutionRecord,
    ShadowLiquidation,
    ShadowOrderTelemetry,
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
    ) -> None:
        self._controller = controller
        self._engine = engine
        self._root = data_root
        self._book_feed = book_feed
        self._context = context
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
            submitted_at=_timestamp(command.submitted_at),
        )

    @property
    def last_fill_count(self) -> int:
        """Return the exact fill-event count from the latest controller cycle."""
        return self._last_fill_count

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
        return action

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
            if command.order_role == "target":
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
        self._engine.apply_market_fill(
            feed_ts=event.event_at,
            action=action,
            side=command.side,
            qty=event.last_quantity,
            mark_px=event.fill_price,
            fill_model=PostOnlyLimitFillModel(),
            fee_override_usd=event.fee_usd,
            exit_reason="take_profit_8pct_margin" if action == "close" else None,
            record_metadata=_fill_metadata(event, evidence),
            **self._annotation_kwargs(command.client_order_id),
        )
        return action

    def _record_order_event(
        self,
        command: OrderCommand,
        event: VenueOrderEvent,
    ) -> None:
        if command.limit_price is None:
            raise RuntimeError("event-shadow order has no limit price")
        self._engine.record_order_event(
            feed_ts=event.event_at,
            action=_order_action(command, event),
            side=command.side,
            qty=command.quantity,
            limit_px=command.limit_price,
            status=event.event_type,
            reason=event.reason,
            record_metadata=_order_metadata(
                event,
                self._controller.port.order_telemetry(event.client_order_id),
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
        mark = position.avg_px if position.avg_px > 0.0 else 1.0
        append_paper_decision(
            self._root,
            {
                "feed_ts": self._controller.port.account_snapshot().observed_at,
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
                "realized_pnl": position.realized_pnl,
                "unrealized_pnl": 0.0,
                "equity": self._engine.equity(mark_px=mark),
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


def book_snapshot_from_event(event: L2SnapshotEvent) -> BookSnapshot:
    """Project normalized L2 evidence into existing backend book telemetry."""
    return BookSnapshot(
        symbol=event.symbol,
        bids=tuple(BookLevel(level.price, level.size) for level in event.bids),
        asks=tuple(BookLevel(level.price, level.size) for level in event.asks),
        ts_recv_ms=event.received_ts_ns / 1_000_000,
        ts_exchange_ms=float(event.exchange_ts_ms),
        source=event.source,
    )


def _fill_metadata(
    event: VenueOrderEvent,
    evidence: ShadowExecutionRecord,
) -> dict[str, object]:
    return {
        "client_order_id": event.client_order_id,
        "venue_order_id": event.venue_order_id,
        "venue_event_type": event.event_type,
        "execution_model": evidence.execution_model,
        "execution_data_source": evidence.data_source,
        "execution_evidence_fresh": evidence.evidence_fresh,
        "execution_event_freshness_ms": evidence.event_freshness_ms,
        "execution_submit_latency_ms": evidence.configured_latency_ms,
        "execution_queue_ahead_qty": evidence.queue_ahead_quantity,
        "execution_requested_qty": evidence.requested_quantity,
        "cumulative_filled_qty": evidence.cumulative_filled_quantity,
        "remaining_qty": evidence.remaining_quantity,
        "liquidity_side": evidence.liquidity_side,
        "margin_model": evidence.margin_model,
    }


def _order_metadata(
    event: VenueOrderEvent,
    telemetry: ShadowOrderTelemetry,
) -> dict[str, object]:
    return {
        "client_order_id": event.client_order_id,
        "venue_order_id": event.venue_order_id,
        "venue_event_type": event.event_type,
        "execution_model": telemetry.execution_model,
        "execution_data_source": telemetry.data_source,
        "execution_evidence_fresh": telemetry.evidence_fresh,
        "execution_submit_latency_ms": telemetry.configured_submit_latency_ms,
        "execution_cancel_latency_ms": telemetry.configured_cancel_latency_ms,
        "execution_queue_ahead_qty": telemetry.queue_ahead_quantity,
        "cumulative_filled_qty": telemetry.cumulative_filled_quantity,
        "remaining_qty": telemetry.remaining_quantity,
        "margin_model": telemetry.margin_model,
    }


def _order_action(command: OrderCommand, event: VenueOrderEvent) -> str:
    role = command.order_role
    if event.event_type == "submitted":
        return f"submit_{role}"
    if event.event_type in {"canceled", "expired"}:
        return f"cancel_{role}"
    return f"{event.event_type}_{role}"


def _timestamp(value: str) -> pd.Timestamp:
    return pd.Timestamp(value)
