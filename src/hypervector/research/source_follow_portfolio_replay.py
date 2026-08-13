"""Continuous source-follow replay through the production shadow matcher."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.nautilus.hyperliquid_margin import maintenance_rate_for_max_leverage
from hypervector.nautilus.hypervelocity_sim import HypervelocitySimulationConfig
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
    ShadowCycle,
)
from hypervector.paper.maker_execution import quantize_size_down
from hypervector.paper.nautilus_shadow import NautilusShadowExecutionPort
from hypervector.research.source_follow_portfolio_models import (
    SourceDirection,
    SourcePortfolioEvent,
    SourcePortfolioReplayConfig,
    SourcePortfolioReport,
    SourcePortfolioTrade,
    SourceReplayFunding,
    SourceReplayMark,
    SourceSignal,
    SourceTradeStatus,
    utc_ms,
)
from hypervector.strategies.hypervelocity_runtime import RuntimeMarketState


@dataclass
class _OpenOutcome:
    baseline_equity: float
    signal_time_utc: str
    entry_time_utc: str
    entry_price: float
    entry_quantity: float
    liquidation_price: float
    direction: SourceDirection
    funding_cashflow: float = 0.0


class _SignalSchedule:
    def __init__(self, signals: tuple[SourceSignal, ...], pulse_seconds: float) -> None:
        self.signals = signals
        self.times = tuple(utc_ms(signal.decision_time_utc) for signal in signals)
        if self.times != tuple(sorted(self.times)) or len(set(self.times)) != len(
            self.times
        ):
            raise ValueError("source signals must be unique and chronological")
        self.pulse_ms = int(pulse_seconds * 1_000)

    def active_signal(self, timestamp_ms: int) -> SourceSignal | None:
        """Return the immutable source signal active at one event timestamp."""
        position = bisect_right(self.times, timestamp_ms) - 1
        if position < 0 or timestamp_ms >= self.times[position] + self.pulse_ms:
            return None
        return self.signals[position]


class _PortfolioTracker:
    def __init__(self, initial_equity: float) -> None:
        self.initial_equity = initial_equity
        self.peak_equity = initial_equity
        self.maximum_drawdown_pct = 0.0
        self.submitted_entries = 0
        self.entry_filled_quantity = 0.0
        self.maker_fees = 0.0
        self.taker_fees = 0.0
        self.funding_cashflow = 0.0
        self.liquidations = 0
        self.partial_liquidations = 0
        self.missing_oracle_settlements = 0
        self.stale_oracle_settlements = 0
        self.execution_uncertainty_annotations = 0
        self.trades: list[SourcePortfolioTrade] = []
        self.open_outcome: _OpenOutcome | None = None
        self.entry_signals: dict[str, SourceSignal] = {}

    def apply_cycle(
        self,
        controller: HypervelocityShadowController,
        cycle: ShadowCycle,
        before_quantity: float,
        before_equity: float,
        observed_at: str,
        active_signal: SourceSignal | None,
    ) -> None:
        """Accumulate commands, fills, and flat/open state transitions."""
        for command in cycle.commands:
            if command.order_role != "entry":
                continue
            if active_signal is None:
                raise RuntimeError("entry command has no active source signal")
            self.submitted_entries += 1
            self.entry_signals[command.client_order_id] = active_signal
        self.execution_uncertainty_annotations += cycle.annotations.count(
            "execution_evidence_uncertain"
        )
        reason: SourceTradeStatus = "target_completed"
        entry_signal: SourceSignal | None = None
        for record in cycle.execution_records:
            command = controller.command_for(record.event.client_order_id)
            fee = record.event.fee_usd
            if record.liquidity_side == "maker":
                self.maker_fees += fee
            else:
                self.taker_fees += fee
            if command.order_role == "entry":
                self.entry_filled_quantity += record.event.last_quantity
                entry_signal = self.entry_signals.get(command.client_order_id)
                if entry_signal is None:
                    raise RuntimeError("entry fill has no source signal identity")
            elif command.order_role == "exit":
                reason = "time_exited"
        self._transition(
            controller,
            before_quantity,
            before_equity,
            observed_at,
            reason,
            entry_signal,
        )

    def apply_funding(self, cashflow: float) -> None:
        """Accumulate one signed funding transfer."""
        self.funding_cashflow += cashflow
        if self.open_outcome is not None:
            self.open_outcome.funding_cashflow += cashflow

    def apply_liquidation(
        self,
        controller: HypervelocityShadowController,
        before_quantity: float,
        before_equity: float,
        observed_at: str,
        fee: float,
    ) -> None:
        """Record one production liquidation attempt and its state change."""
        self.taker_fees += fee
        if controller.state.position_quantity > 1e-12:
            self.partial_liquidations += 1
            return
        self.liquidations += 1
        self._transition(
            controller,
            before_quantity,
            before_equity,
            observed_at,
            "liquidated",
        )

    def mark_equity(self, equity: float) -> None:
        """Update causal peak-to-trough marked drawdown."""
        self.peak_equity = max(self.peak_equity, equity)
        if self.peak_equity <= 0.0:
            return
        drawdown = 100.0 * (equity - self.peak_equity) / self.peak_equity
        self.maximum_drawdown_pct = min(self.maximum_drawdown_pct, drawdown)

    def _transition(
        self,
        controller: HypervelocityShadowController,
        before_quantity: float,
        before_equity: float,
        observed_at: str,
        reason: SourceTradeStatus,
        entry_signal: SourceSignal | None = None,
    ) -> None:
        after = controller.state.position_quantity
        if before_quantity <= 1e-12 and after > 1e-12:
            if entry_signal is None:
                raise RuntimeError("opened position has no source signal identity")
            opened_at = controller.state.position_opened_at or observed_at
            average, liquidation = _entry_economics(controller)
            self.open_outcome = _OpenOutcome(
                before_equity,
                entry_signal.decision_time_utc,
                opened_at,
                average,
                after,
                liquidation,
                entry_signal.direction,
            )
        elif entry_signal is not None and after > 1e-12:
            opened = self.open_outcome
            if opened is None:
                raise RuntimeError("entry fill has no tracked open outcome")
            average, liquidation = _entry_economics(controller)
            opened.entry_price = average
            opened.entry_quantity = max(opened.entry_quantity, after)
            opened.liquidation_price = liquidation
        if before_quantity <= 1e-12 or after > 1e-12:
            return
        opened = self.open_outcome
        if opened is None:
            raise RuntimeError("position closed without tracked open state")
        equity = controller.port.account_snapshot().equity_usd
        self.trades.append(
            SourcePortfolioTrade(
                opened.direction,
                opened.signal_time_utc,
                opened.entry_time_utc,
                observed_at,
                reason,
                opened.entry_price,
                opened.entry_quantity,
                opened.liquidation_price,
                equity - opened.baseline_equity,
                opened.funding_cashflow,
            )
        )
        self.open_outcome = None


class SourcePortfolioReplaySession:
    """Retain production execution state across sparse archive windows."""

    def __init__(
        self,
        signals: tuple[SourceSignal, ...],
        config: SourcePortfolioReplayConfig | None = None,
    ) -> None:
        self._config = config or SourcePortfolioReplayConfig()
        self._schedule = _SignalSchedule(signals, self._config.entry_pulse_seconds)
        self._controller = _controller(self._config)
        self._tracker = _PortfolioTracker(self._config.initial_equity)
        self._latest_oracle: tuple[int, float] | None = None
        self._last_timestamp = -1

    @property
    def is_idle(self) -> bool:
        """Return whether no order or position requires continuous evidence."""
        state = self._controller.state
        return (
            state.pending_entry is None
            and state.position_quantity <= 1e-12
            and not state.active_targets
        )

    @property
    def config(self) -> SourcePortfolioReplayConfig:
        """Return the immutable execution contract applied by this session."""
        return self._config

    def apply(self, event: SourcePortfolioEvent) -> None:
        """Apply one chronological production or context event."""
        timestamp = _event_ms(event)
        if timestamp < self._last_timestamp:
            raise ValueError("source portfolio events must be chronological")
        self._last_timestamp = timestamp
        self._latest_oracle = _apply_event(
            self._controller,
            self._tracker,
            event,
            self._schedule,
            self._config,
            self._latest_oracle,
        )
        equity = self._controller.port.account_snapshot().equity_usd
        self._tracker.mark_equity(equity)

    def apply_all(self, events: Iterable[SourcePortfolioEvent]) -> None:
        """Apply one already-bounded chronological event sequence."""
        for event in events:
            self.apply(event)

    def report(self) -> SourcePortfolioReport:
        """Project current continuous state into an auditable report."""
        return _report(
            self._controller,
            self._tracker,
            self._schedule,
            self._config,
        )


def replay_source_portfolio(
    events: Iterable[SourcePortfolioEvent],
    signals: tuple[SourceSignal, ...],
    config: SourcePortfolioReplayConfig | None = None,
) -> SourcePortfolioReport:
    """Replay a continuous source signal set through production execution state."""
    session = SourcePortfolioReplaySession(signals, config)
    session.apply_all(events)
    return session.report()


def _apply_event(
    controller: HypervelocityShadowController,
    tracker: _PortfolioTracker,
    event: SourcePortfolioEvent,
    schedule: _SignalSchedule,
    config: SourcePortfolioReplayConfig,
    latest_oracle: tuple[int, float] | None,
) -> tuple[int, float] | None:
    before_quantity = controller.state.position_quantity
    before_equity = controller.port.account_snapshot().equity_usd
    observed_at = _iso_ms(_event_ms(event))
    if isinstance(event, SourceReplayMark):
        _apply_mark(controller, tracker, event, before_quantity, before_equity)
        return event.ts_ms, event.oracle_price
    if isinstance(event, SourceReplayFunding):
        _apply_funding(controller, tracker, event, config, latest_oracle)
        return latest_oracle
    cycle = controller.ingest(event)
    tracker.apply_cycle(
        controller,
        cycle,
        before_quantity,
        before_equity,
        observed_at,
        schedule.active_signal(_event_ms(event)),
    )
    if isinstance(event, L2SnapshotEvent):
        before_quantity = controller.state.position_quantity
        before_equity = controller.port.account_snapshot().equity_usd
        cycle = controller.on_market(_market(event, controller, schedule, config))
        tracker.apply_cycle(
            controller,
            cycle,
            before_quantity,
            before_equity,
            observed_at,
            schedule.active_signal(event.exchange_ts_ms),
        )
    return latest_oracle


def _apply_mark(
    controller: HypervelocityShadowController,
    tracker: _PortfolioTracker,
    event: SourceReplayMark,
    before_quantity: float,
    before_equity: float,
) -> None:
    liquidated = controller.port.mark(
        mark_price=event.mark_price,
        observed_at=_iso_ms(event.ts_ms),
    )
    if not liquidated:
        return
    liquidation = controller.port.last_liquidation
    if liquidation is None:
        raise RuntimeError("liquidation result disappeared")
    controller.reconcile_liquidation(_iso_ms(event.ts_ms))
    tracker.apply_liquidation(
        controller,
        before_quantity,
        before_equity,
        _iso_ms(event.ts_ms),
        liquidation.execution_fee_usd,
    )


def _apply_funding(
    controller: HypervelocityShadowController,
    tracker: _PortfolioTracker,
    event: SourceReplayFunding,
    config: SourcePortfolioReplayConfig,
    latest_oracle: tuple[int, float] | None,
) -> None:
    if controller.state.position_quantity <= 1e-12:
        return
    if latest_oracle is None:
        tracker.missing_oracle_settlements += 1
        return
    oracle_ms, oracle = latest_oracle
    if event.ts_ms - oracle_ms > config.maximum_oracle_age_ms:
        tracker.stale_oracle_settlements += 1
        return
    cashflow = controller.port.apply_funding(
        hourly_rate=event.funding_rate,
        mark_price=oracle,
        applied_at=_iso_ms(event.ts_ms),
    )
    tracker.apply_funding(cashflow)


def _market(
    event: L2SnapshotEvent,
    controller: HypervelocityShadowController,
    schedule: _SignalSchedule,
    config: SourcePortfolioReplayConfig,
) -> RuntimeMarketState:
    active = schedule.active_signal(event.exchange_ts_ms)
    direction = active.direction if active is not None else None
    limit = (
        event.bids[0].price
        if direction == "long"
        else (event.asks[0].price if direction == "short" else None)
    )
    equity = controller.port.account_snapshot().equity_usd
    sizing_price = limit or event.asks[0].price
    risk_fraction = config.margin_fraction * (
        active.allocation_multiplier if active else 1.0
    )
    raw_quantity = equity * risk_fraction * config.leverage / sizing_price
    quantity = quantize_size_down(raw_quantity, size_decimals=config.size_decimals)
    minimum = 10 ** (-config.size_decimals)
    return RuntimeMarketState(
        symbol="BTC",
        observed_at=_iso_ms(event.exchange_ts_ms),
        entry_direction=direction,
        structural_direction=direction,
        entry_quantity=max(quantity, minimum),
        entry_limit_price=limit,
        evidence_fresh=True,
        entry_ttl_seconds=config.entry_ttl_seconds,
        reentry_cooldown_seconds=0.0,
        target_price_fraction=config.target_price_fraction,
        price_tick=config.price_tick,
        maximum_hold_seconds=config.maximum_hold_seconds if active else None,
    )


def _controller(config: SourcePortfolioReplayConfig) -> HypervelocityShadowController:
    port = NautilusShadowExecutionPort(
        symbol="BTC",
        initial_cash_usd=config.initial_equity,
        simulation_config=HypervelocitySimulationConfig(
            submit_latency_ms=config.submit_latency_ms,
            cancel_latency_ms=config.cancel_latency_ms,
            update_latency_ms=50,
            default_leverage=int(config.leverage),
        ),
        maker_fee_rate=config.maker_fee_rate,
        taker_fee_rate=config.taker_fee_rate,
        leverage=config.leverage,
        maintenance_rate=maintenance_rate_for_max_leverage(config.leverage),
        max_event_age_ms=config.max_event_age_ms,
    )
    neutral = RuntimeMarketState(
        symbol="BTC",
        observed_at="1970-01-01T00:00:00+00:00",
        entry_direction=None,
        structural_direction=None,
        entry_quantity=10 ** (-config.size_decimals),
        entry_limit_price=None,
        evidence_fresh=False,
        entry_ttl_seconds=config.entry_ttl_seconds,
        reentry_cooldown_seconds=0.0,
        target_price_fraction=config.target_price_fraction,
        price_tick=config.price_tick,
        maximum_hold_seconds=None,
    )
    return HypervelocityShadowController(port=port, initial_market=neutral)


def _report(
    controller: HypervelocityShadowController,
    tracker: _PortfolioTracker,
    schedule: _SignalSchedule,
    config: SourcePortfolioReplayConfig,
) -> SourcePortfolioReport:
    gains = sum(max(trade.net_pnl, 0.0) for trade in tracker.trades)
    losses = -sum(min(trade.net_pnl, 0.0) for trade in tracker.trades)
    return SourcePortfolioReport(
        initial_equity=config.initial_equity,
        final_equity=controller.port.account_snapshot().equity_usd,
        signal_count=len(schedule.signals),
        submitted_entries=tracker.submitted_entries,
        entry_filled_quantity=tracker.entry_filled_quantity,
        completed_trades=len(tracker.trades),
        target_completions=sum(
            trade.status == "target_completed" for trade in tracker.trades
        ),
        time_exits=sum(trade.status == "time_exited" for trade in tracker.trades),
        liquidations=tracker.liquidations,
        partial_liquidations=tracker.partial_liquidations,
        open_positions=int(controller.state.position_quantity > 1e-12),
        maker_fees=tracker.maker_fees,
        taker_fees=tracker.taker_fees,
        funding_cashflow=tracker.funding_cashflow,
        profit_factor=(gains / losses if losses > 0.0 else None),
        maximum_drawdown_pct=tracker.maximum_drawdown_pct,
        missing_oracle_settlements=tracker.missing_oracle_settlements,
        stale_oracle_settlements=tracker.stale_oracle_settlements,
        execution_uncertainty_annotations=(tracker.execution_uncertainty_annotations),
        trades=tuple(tracker.trades),
        limitations=(
            "Displayed L2 is a public queue proxy; private cancellations are unknown.",
            (
                "Recorder receive timestamps are preserved."
                if config.receipt_timestamp_source == "recorded"
                else "Archive receipt timestamps equal exchange timestamps."
            ),
            "Source label parity is proven separately from this execution replay.",
        ),
    )


def _event_ms(event: SourcePortfolioEvent) -> int:
    if isinstance(event, (SourceReplayMark, SourceReplayFunding)):
        return event.ts_ms
    return event.exchange_ts_ms


def _iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000, tz=UTC).isoformat()


def _entry_economics(controller: HypervelocityShadowController) -> tuple[float, float]:
    average = controller.state.position_average_price
    liquidation = controller.port.liquidation_price
    if average is None or liquidation is None:
        raise RuntimeError("open position is missing entry economics")
    return average, liquidation
