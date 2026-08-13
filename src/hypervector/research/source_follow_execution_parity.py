"""Replay one source-follow lifecycle through the production event runtime."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import duckdb

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent
from hypervector.nautilus.hyperliquid_margin import maintenance_rate_for_max_leverage
from hypervector.nautilus.hypervelocity_sim import HypervelocitySimulationConfig
from hypervector.paper.nautilus_shadow import NautilusShadowExecutionPort
from hypervector.paper.shadow_execution_models import ShadowExecutionRecord
from hypervector.research.source_follow_archive_events import (
    archive_book_event,
    archive_book_rows,
    archive_event_sort_key,
    archive_trade_event,
    archive_trade_rows,
)
from hypervector.research.source_follow_portfolio_models import (
    SOURCE_FOLLOW_MAX_EVENT_AGE_MS,
)
from hypervector.strategies.hypervelocity_runtime import RuntimeMarketState
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
)

ReplayEvent = L2SnapshotEvent | PublicTradeEvent
Direction = Literal["long", "short"]


@dataclass(frozen=True)
class SourceLifecycleSpec:
    """Frozen entry and exit assumptions for one source-follow event."""

    signal_time_utc: str
    direction: Direction
    quantity: float
    entry_pulse_seconds: float = 60.0
    entry_ttl_seconds: float = 60.0
    target_price_fraction: float = 8.0 / 30.0 / 100.0
    maximum_hold_seconds: float = 86_400.0


@dataclass(frozen=True)
class SourceLifecycleExecution:
    """Production-runtime execution facts for one bounded replay."""

    status: str
    requested_quantity: float
    submitted_at: str | None
    entry_first_at: str | None
    entry_completed_at: str | None
    entry_price: float | None
    entry_filled_quantity: float
    entry_fill_count: int
    exit_completed_at: str | None
    exit_price: float | None
    exit_filled_quantity: float
    exit_fill_count: int
    final_position_quantity: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable result."""
        return asdict(self)


def replay_source_lifecycle(
    events: Sequence[ReplayEvent],
    spec: SourceLifecycleSpec,
) -> SourceLifecycleExecution:
    """Replay normalized archive events through production order state."""
    ordered = _validated_events(events)
    signal_ms = _timestamp_ms(spec.signal_time_utc)
    first_book = next(
        (
            event
            for event in ordered
            if isinstance(event, L2SnapshotEvent) and event.exchange_ts_ms >= signal_ms
        ),
        None,
    )
    if first_book is None:
        raise ValueError("source lifecycle has no book at or after signal")
    controller = _controller(spec)
    records: list[ShadowExecutionRecord] = []
    submitted_at: str | None = None
    was_open = False
    for event in ordered:
        if event.exchange_ts_ms < signal_ms:
            continue
        cycle = controller.ingest(event)
        records.extend(cycle.execution_records)
        if isinstance(event, L2SnapshotEvent):
            market = _market_state(event, spec)
            decision = controller.on_market(market)
            records.extend(decision.execution_records)
            if submitted_at is None:
                submitted_at = next(
                    (
                        command.submitted_at
                        for command in decision.commands
                        if command.order_role == "entry"
                    ),
                    None,
                )
        was_open = was_open or controller.state.position_quantity > 0.0
        if was_open and controller.state.position_quantity == 0.0:
            break
    return _execution_result(controller, records, submitted_at, spec.quantity)


def load_archive_events(
    database_path: Path,
    *,
    symbol: str,
    start_utc: str,
    end_utc: str,
) -> tuple[ReplayEvent, ...]:
    """Load one bounded, read-only canonical L2/trade event sequence."""
    if not database_path.is_file():
        raise FileNotFoundError(f"research database is missing: {database_path}")
    start = _utc(start_utc)
    end = _utc(end_utc)
    if start >= end:
        raise ValueError("archive event window must be positive")
    with duckdb.connect(str(database_path), read_only=True) as connection:
        books = archive_book_rows(connection, symbol, start, end)
        trades = archive_trade_rows(connection, symbol, start, end)
    events = [*(archive_book_event(symbol, row) for row in books)]
    events.extend(archive_trade_event(symbol, row) for row in trades)
    return tuple(sorted(events, key=archive_event_sort_key))


def _controller(spec: SourceLifecycleSpec) -> HypervelocityShadowController:
    port = NautilusShadowExecutionPort(
        symbol="BTC",
        initial_cash_usd=15_000.0,
        simulation_config=HypervelocitySimulationConfig(
            submit_latency_ms=50,
            cancel_latency_ms=50,
            update_latency_ms=50,
            default_leverage=30,
        ),
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        leverage=30.0,
        maintenance_rate=maintenance_rate_for_max_leverage(30.0),
        max_event_age_ms=SOURCE_FOLLOW_MAX_EVENT_AGE_MS,
    )
    neutral = RuntimeMarketState(
        symbol="BTC",
        observed_at=spec.signal_time_utc,
        entry_direction=None,
        structural_direction=None,
        entry_quantity=spec.quantity,
        entry_limit_price=None,
        evidence_fresh=False,
        entry_ttl_seconds=spec.entry_ttl_seconds,
        reentry_cooldown_seconds=0.0,
        target_price_fraction=spec.target_price_fraction,
        price_tick=1.0,
        maximum_hold_seconds=spec.maximum_hold_seconds,
    )
    return HypervelocityShadowController(port=port, initial_market=neutral)


def _market_state(
    event: L2SnapshotEvent,
    spec: SourceLifecycleSpec,
) -> RuntimeMarketState:
    observed_at = _iso_ms(event.exchange_ts_ms)
    elapsed = (event.exchange_ts_ms - _timestamp_ms(spec.signal_time_utc)) / 1_000
    eligible = 0.0 <= elapsed < spec.entry_pulse_seconds
    direction = spec.direction if eligible else None
    limit = None
    if direction == "long":
        limit = event.bids[0].price
    elif direction == "short":
        limit = event.asks[0].price
    return RuntimeMarketState(
        symbol="BTC",
        observed_at=observed_at,
        entry_direction=direction,
        structural_direction=spec.direction,
        entry_quantity=spec.quantity,
        entry_limit_price=limit,
        evidence_fresh=True,
        entry_ttl_seconds=spec.entry_ttl_seconds,
        reentry_cooldown_seconds=0.0,
        target_price_fraction=spec.target_price_fraction,
        price_tick=1.0,
        maximum_hold_seconds=spec.maximum_hold_seconds,
    )


def _execution_result(
    controller: HypervelocityShadowController,
    records: Sequence[ShadowExecutionRecord],
    submitted_at: str | None,
    requested_quantity: float,
) -> SourceLifecycleExecution:
    entry = [record for record in records if _role(controller, record) == "entry"]
    exits = [record for record in records if _role(controller, record) != "entry"]
    entry_quantity = sum(record.event.last_quantity for record in entry)
    exit_quantity = sum(record.event.last_quantity for record in exits)
    final_quantity = controller.state.position_quantity
    if entry_quantity <= 0.0:
        status = "no_fill"
    elif final_quantity > 0.0:
        status = "open"
    elif entry_quantity < requested_quantity - 1e-12:
        status = "partial_completed"
    else:
        status = "completed"
    return SourceLifecycleExecution(
        status=status,
        requested_quantity=requested_quantity,
        submitted_at=submitted_at,
        entry_first_at=entry[0].event.event_at if entry else None,
        entry_completed_at=entry[-1].event.event_at if entry else None,
        entry_price=entry[0].event.fill_price if entry else None,
        entry_filled_quantity=entry_quantity,
        entry_fill_count=len(entry),
        exit_completed_at=exits[-1].event.event_at if exits else None,
        exit_price=exits[-1].event.fill_price if exits else None,
        exit_filled_quantity=exit_quantity,
        exit_fill_count=len(exits),
        final_position_quantity=final_quantity,
    )


def _role(
    controller: HypervelocityShadowController,
    record: ShadowExecutionRecord,
) -> str:
    return controller.command_for(record.event.client_order_id).order_role


def _validated_events(events: Sequence[ReplayEvent]) -> tuple[ReplayEvent, ...]:
    if not events:
        raise ValueError("source lifecycle replay requires events")
    ordered = tuple(sorted(events, key=archive_event_sort_key))
    if tuple(events) != ordered:
        raise ValueError("source lifecycle events must be chronological")
    if any(event.symbol != "BTC" for event in ordered):
        raise ValueError("source lifecycle replay requires BTC events")
    return ordered


def _timestamp_ms(value: str) -> int:
    return int(_utc(value).timestamp() * 1_000)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0.0:
        raise ValueError("source lifecycle timestamps must be UTC")
    return parsed.astimezone(UTC)


def _iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000, tz=UTC).isoformat()
