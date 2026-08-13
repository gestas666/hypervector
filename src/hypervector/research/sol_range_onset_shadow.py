"""No-submit forward shadow lifecycle for the SOL range-onset candidate."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from hypervector.data.hl_events import AssetContextEvent, L2SnapshotEvent, StreamGap
from hypervector.research.range_onset_event_models import (
    EventExitReason,
    EventSignal,
)
from hypervector.research.range_onset_event_risk import (
    EventRiskPosition,
    liquidation_price,
)
from hypervector.research.shared_portfolio_models import Direction
from hypervector.research.sol_range_onset_shadow_models import (
    ShadowStatus,
    SharedCapitalSnapshot,
    SolShadowConfig,
    SolShadowPosition,
    SolShadowSnapshot,
    SolShadowTrade,
)
from hypervector.research.sol_range_onset_shadow_math import (
    HOUR_MS,
    barrier_crossed,
    depth_fill,
    desired_direction,
    event_config,
    hour_floor,
    risk_position,
    stop_price,
)
from hypervector.research.sol_range_onset_shadow_state import (
    RestoredSolShadowState,
    export_sol_shadow_state,
    restore_sol_shadow_state,
)


class SolRangeOnsetShadowEngine:
    """Apply decisions to public depth while remaining execution-incapable."""

    def __init__(self, config: SolShadowConfig | None = None) -> None:
        self._config = config or SolShadowConfig()
        self._capital: SharedCapitalSnapshot | None = None
        self._status: ShadowStatus = "active"
        self._delta = 0.0
        self._position: SolShadowPosition | None = None
        self._pending_entry: EventSignal | None = None
        self._pending_exit_reason: EventExitReason | None = None
        self._pending_exit_time_ms: int | None = None
        self._pending_reversal: EventSignal | None = None
        self._last_funding_hour_ms: int | None = None
        self._trades: list[SolShadowTrade] = []
        self._records: list[dict[str, object]] = []

    @property
    def snapshot(self) -> SolShadowSnapshot:
        """Return an immutable view of current shadow state."""
        return SolShadowSnapshot(
            self._status,
            self._delta,
            self._position,
            self._pending_entry,
            self._pending_exit_reason,
            self._pending_reversal,
            tuple(self._trades),
        )

    @property
    def config_fingerprint(self) -> str:
        """Return a stable identity for restart compatibility checks."""
        return self._config.fingerprint

    def export_state(self) -> dict[str, object]:
        """Return a JSON-safe complete lifecycle snapshot."""
        return export_sol_shadow_state(
            config=self._config,
            state=self._persistence_state(),
        )

    @classmethod
    def from_state(
        cls,
        config: SolShadowConfig,
        payload: Mapping[str, object],
    ) -> SolRangeOnsetShadowEngine:
        """Restore a validated complete lifecycle snapshot."""
        restored = restore_sol_shadow_state(config, payload)
        engine = cls(config)
        engine._restore_values(restored)
        return engine

    def _persistence_state(self) -> RestoredSolShadowState:
        return RestoredSolShadowState(
            self._status,
            self._delta,
            self._capital,
            self._position,
            self._pending_entry,
            self._pending_exit_reason,
            self._pending_exit_time_ms,
            self._pending_reversal,
            self._last_funding_hour_ms,
            tuple(self._trades),
        )

    def _restore_values(self, restored: RestoredSolShadowState) -> None:
        self._status = restored.status
        self._delta = restored.delta_usd
        self._capital = restored.capital
        self._position = restored.position
        self._pending_entry = restored.pending_entry
        self._pending_exit_reason = restored.pending_exit_reason
        self._pending_exit_time_ms = restored.pending_exit_time_ms
        self._pending_reversal = restored.pending_reversal
        self._last_funding_hour_ms = restored.last_funding_hour_ms
        self._trades = list(restored.completed_trades)

    def update_shared_capital(self, snapshot: SharedCapitalSnapshot) -> None:
        """Install the latest backend-authoritative shared-capital telemetry."""
        self._capital = snapshot

    def ingest_decision(
        self,
        decision: EventSignal,
        *,
        fresh_at_observation: bool = True,
    ) -> None:
        """Schedule an unambiguous entry, exit, or close-and-reverse decision."""
        if not isinstance(fresh_at_observation, bool):
            raise ValueError("fresh_at_observation must be boolean")
        if self._status != "active":
            return
        if not fresh_at_observation:
            self._ingest_stale_decision(decision)
            return
        desired = desired_direction(decision)
        position = self._position
        if position is not None:
            self._schedule_position_decision(decision, desired, position)
            return
        if desired is not None:
            self._pending_entry = decision

    def _ingest_stale_decision(self, decision: EventSignal) -> None:
        desired = desired_direction(decision)
        position = self._position
        if position is None:
            if desired is not None:
                self._record(
                    "stale_entry_ignored",
                    decision.decision_time_ms,
                    decision_time_ms=decision.decision_time_ms,
                )
            return
        opposite = desired is not None and desired != position.direction
        exits_side = (position.direction == "long" and decision.long_exit) or (
            position.direction == "short" and decision.short_exit
        )
        if self._pending_exit_reason is not None or not (opposite or exits_side):
            return
        self._pending_exit_reason = "opposite_signal" if opposite else "signal"
        self._pending_exit_time_ms = decision.decision_time_ms
        action = (
            "stale_opposite_signal_exit_triggered"
            if opposite
            else "stale_signal_exit_triggered"
        )
        self._record(action, decision.decision_time_ms)

    def ingest_event(
        self,
        event: L2SnapshotEvent | AssetContextEvent | StreamGap,
    ) -> None:
        """Apply public mark and depth evidence to the active lifecycle."""
        if event.symbol != "SOL":
            raise ValueError(
                f"SOL shadow event symbol must be SOL, got {event.symbol!r}"
            )
        if isinstance(event, StreamGap):
            self._ingest_gap(event)
            return
        if isinstance(event, AssetContextEvent):
            self._ingest_context(event)
            return
        self._schedule_maximum_hold(event)
        if self._pending_exit_reason is not None:
            self._fill_exit(event)
            return
        pending = self._pending_entry
        if self._status != "active" or pending is None:
            return
        if event.exchange_ts_ms < pending.decision_time_ms:
            return
        self._fill_entry(event, pending)

    def _ingest_gap(self, event: StreamGap) -> None:
        active = (
            self._position is not None
            or self._pending_entry is not None
            or self._pending_exit_reason is not None
        )
        action = "active_stream_gap" if active else "flat_stream_gap"
        if active:
            self._status = "evidence_failed"
        self._record(
            action,
            event.detected_ts_ns // 1_000_000,
            reason=event.reason,
            previous_exchange_ts_ms=event.previous_exchange_ts_ms,
            next_exchange_ts_ms=event.next_exchange_ts_ms,
        )

    def _schedule_maximum_hold(self, event: L2SnapshotEvent) -> None:
        position = self._position
        if position is None or self._pending_exit_reason is not None:
            return
        deadline = position.entry_time_ms + self._config.max_hold_ms
        if event.exchange_ts_ms < deadline:
            return
        self._pending_exit_reason = "max_hold"
        self._pending_exit_time_ms = deadline
        self._record("max_hold_triggered", deadline)

    def drain_records(self) -> tuple[dict[str, object], ...]:
        """Drain state-changing telemetry records in causal order."""
        rows = tuple(self._records)
        self._records.clear()
        return rows

    def _fill_entry(self, event: L2SnapshotEvent, decision: EventSignal) -> None:
        capital = self._entry_capital(event)
        if capital is None:
            self._pending_entry = None
            return
        direction: Direction = "long" if decision.long_entry else "short"
        notional = min(
            capital * self._config.margin_fraction * self._config.leverage,
            self._config.notional_cap_usd,
        )
        quantity = notional / decision.reference_price
        fill = depth_fill(event, direction, quantity, entering=True)
        if not fill.complete:
            self._record(
                "entry_depth_rejected",
                event.exchange_ts_ms,
                requested_quantity=quantity,
                visible_filled_quantity=fill.filled_quantity,
            )
            self._pending_entry = None
            return
        margin = notional / self._config.leverage
        fee = quantity * fill.vwap * self._config.taker_fee_rate
        stop = stop_price(direction, fill.vwap, self._config.stop_bps)
        risk = EventRiskPosition(
            direction,
            quantity,
            fill.vwap,
            margin,
            fee,
            event.exchange_ts_ms,
            stop,
        )
        self._delta -= fee
        position = SolShadowPosition(
            direction,
            decision.decision_time_ms,
            event.exchange_ts_ms,
            fill.vwap,
            decision.reference_price,
            quantity,
            notional,
            margin,
            fee,
            stop,
            liquidation_price(risk, event_config(self._config), 0.0),
        )
        self._position = position
        self._last_funding_hour_ms = hour_floor(event.exchange_ts_ms)
        self._pending_entry = None
        self._record(
            "entry_filled",
            event.exchange_ts_ms,
            direction=direction,
            fill_px=fill.vwap,
            fill_qty=quantity,
            position_qty=_signed_quantity(position),
            position_avg_px=fill.vwap,
            leverage=self._config.leverage,
            allocated_margin_usd=margin,
            fee_usd=fee,
            stop_price=stop,
            liquidation_price=position.liquidation_price,
            equity_delta_usd=self._delta,
        )

    def _ingest_context(self, event: AssetContextEvent) -> None:
        self._settle_funding(event)
        position = self._position
        if self._status != "active" or position is None:
            return
        reason: EventExitReason | None = None
        if barrier_crossed(
            position.direction,
            event.mark_price,
            position.liquidation_price,
        ):
            reason = "liquidation"
        elif barrier_crossed(position.direction, event.mark_price, position.stop_price):
            reason = "stop"
        if reason is None or self._pending_exit_reason is not None:
            return
        self._pending_exit_reason = reason
        self._pending_exit_time_ms = event.observed_ts_ms
        self._record(
            f"{reason}_triggered",
            event.observed_ts_ms,
            mark_price=event.mark_price,
            stop_price=position.stop_price,
            liquidation_price=position.liquidation_price,
        )

    def _settle_funding(self, event: AssetContextEvent) -> None:
        position = self._position
        last_hour = self._last_funding_hour_ms
        if position is None or last_hour is None or self._status != "active":
            return
        current_hour = hour_floor(event.observed_ts_ms)
        if current_hour <= last_hour:
            return
        if current_hour > last_hour + HOUR_MS:
            self._status = "evidence_failed"
            self._record(
                "funding_evidence_gap",
                event.observed_ts_ms,
                last_funding_hour_ms=last_hour,
                observed_funding_hour_ms=current_hour,
            )
            return
        sign = 1.0 if position.direction == "long" else -1.0
        cashflow = (
            -sign * position.quantity * event.oracle_price * event.funding_rate_hourly
        )
        cumulative = position.funding_cashflow_usd + cashflow
        risk = risk_position(position)
        updated = replace(
            position,
            funding_cashflow_usd=cumulative,
            liquidation_price=liquidation_price(
                risk,
                event_config(self._config),
                cumulative,
            ),
        )
        self._position = updated
        self._delta += cashflow
        self._last_funding_hour_ms = current_hour
        self._record(
            "funding_settled",
            event.observed_ts_ms,
            funding_rate_hourly=event.funding_rate_hourly,
            funding_reference_price=event.oracle_price,
            funding_reference_source="hyperliquid_oracle_price",
            funding_cashflow_usd=cashflow,
            funding_payment_usd=cashflow,
            position_qty=_signed_quantity(updated),
            position_avg_px=updated.entry_price,
            leverage=self._config.leverage,
            liquidation_price=updated.liquidation_price,
            equity_delta_usd=self._delta,
        )

    def _fill_exit(self, event: L2SnapshotEvent) -> None:
        position = self._position
        reason = self._pending_exit_reason
        trigger_time = self._pending_exit_time_ms
        if position is None or reason is None or trigger_time is None:
            raise RuntimeError("pending SOL exit requires a position and trigger")
        if event.received_ts_ns // 1_000_000 < trigger_time:
            return
        fill = depth_fill(event, position.direction, position.quantity, entering=False)
        if not fill.complete:
            self._status = "evidence_failed"
            self._record(
                "exit_depth_failure",
                event.exchange_ts_ms,
                requested_quantity=position.quantity,
                visible_filled_quantity=fill.filled_quantity,
                exit_reason=reason,
            )
            return
        reversal = self._pending_reversal
        self._close_position(event, fill.vwap, reason)
        self._pending_reversal = None
        if reversal is not None:
            self._fill_entry(event, reversal)

    def _schedule_position_decision(
        self,
        decision: EventSignal,
        desired: Direction | None,
        position: SolShadowPosition,
    ) -> None:
        if self._pending_exit_reason is not None:
            return
        if desired is not None and desired != position.direction:
            self._pending_exit_reason = "opposite_signal"
            self._pending_exit_time_ms = decision.decision_time_ms
            self._pending_reversal = decision
            self._record("opposite_signal_triggered", decision.decision_time_ms)
            return
        exits_side = (position.direction == "long" and decision.long_exit) or (
            position.direction == "short" and decision.short_exit
        )
        if exits_side:
            self._pending_exit_reason = "signal"
            self._pending_exit_time_ms = decision.decision_time_ms
            self._record("signal_exit_triggered", decision.decision_time_ms)

    def _close_position(
        self,
        event: L2SnapshotEvent,
        exit_price: float,
        reason: EventExitReason,
    ) -> None:
        position = self._position
        if position is None:
            raise RuntimeError("SOL close requires an open position")
        sign = 1.0 if position.direction == "long" else -1.0
        gross = sign * position.quantity * (exit_price - position.entry_price)
        exit_fee = position.quantity * exit_price * self._config.taker_fee_rate
        fees = position.entry_fee_usd + exit_fee
        net = gross - fees + position.funding_cashflow_usd
        self._delta += gross - exit_fee
        trade = SolShadowTrade(
            position.direction,
            position.entry_time_ms,
            event.exchange_ts_ms,
            position.entry_price,
            exit_price,
            position.quantity,
            gross,
            fees,
            position.funding_cashflow_usd,
            net,
            reason,
        )
        self._trades.append(trade)
        self._position = None
        self._pending_exit_reason = None
        self._pending_exit_time_ms = None
        self._last_funding_hour_ms = None
        self._record(
            "position_closed",
            event.exchange_ts_ms,
            direction=position.direction,
            fill_px=exit_price,
            fill_qty=position.quantity,
            position_qty=0.0,
            position_avg_px=0.0,
            leverage=self._config.leverage,
            fee_usd=exit_fee,
            trade_net_pnl_usd=trade.net_pnl_usd,
            exit_reason=reason,
            equity_delta_usd=self._delta,
        )

    def _entry_capital(self, event: L2SnapshotEvent) -> float | None:
        capital = self._capital
        event_time = event.received_ts_ns // 1_000_000
        age_ms = None if capital is None else event_time - capital.observed_time_ms
        unavailable = (
            age_ms is None or age_ms < 0 or age_ms > self._config.capital_freshness_ms
        )
        if unavailable:
            self._record(
                "entry_capital_unavailable",
                event.exchange_ts_ms,
                capital_age_ms=age_ms,
            )
            return None
        combined = capital.equity_usd + self._delta
        base = min(combined, self._config.capital_base_cap_usd)
        notional = min(
            base * self._config.margin_fraction * self._config.leverage,
            self._config.notional_cap_usd,
        )
        margin = notional / self._config.leverage
        maximum_fee = notional * self._config.taker_fee_rate * 1.01
        if capital.reserved_margin_usd + margin + maximum_fee > combined:
            self._record(
                "entry_shared_margin_rejected",
                event.exchange_ts_ms,
                combined_equity_usd=combined,
                reserved_margin_usd=capital.reserved_margin_usd,
                required_margin_usd=margin,
                estimated_entry_fee_usd=maximum_fee,
            )
            return None
        return base

    def _record(self, action: str, event_time_ms: int, **fields: object) -> None:
        row: dict[str, object] = {
            "schema_version": 1,
            "action": action,
            "event_time_ms": event_time_ms,
            "execution_authority": "none",
            "submitted": False,
            "place_attempted": False,
        }
        row.update(fields)
        self._records.append(row)


def _signed_quantity(position: SolShadowPosition) -> float:
    sign = 1.0 if position.direction == "long" else -1.0
    return sign * position.quantity
