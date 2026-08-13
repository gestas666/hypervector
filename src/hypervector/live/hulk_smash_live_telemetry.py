"""Authoritative ledger projection for Hulk observation and execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from hypervector.live.hulk_smash_live_config import HulkSmashLiveConfig
from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_ledger import HulkSmashLiveLedger
from hypervector.live.hulk_smash_live_metrics import HulkSmashExecutionMetrics
from hypervector.live.hulk_smash_live_protocol import HulkSmashVenueProtocol
from hypervector.live.hyperliquid_fill_identity import fill_trade_id, ledger_trade_id
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolBookSnapshot,
    SolFill,
    SolFundingPayment,
    SolOpenOrder,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)


class HulkSmashLiveTelemetryError(RuntimeError):
    """Hulk telemetry cannot produce a truthful JSON ledger record."""


class HulkSmashLiveTelemetry:
    """Write strategy-attributed observations without exposing secrets."""

    def __init__(
        self,
        *,
        config: HulkSmashLiveConfig,
        ledger: HulkSmashLiveLedger,
        armed: bool,
        wallet_configured: bool,
        signing_key_configured: bool,
        now_fn: Callable[[], datetime],
    ) -> None:
        if config.backend_ledger != ledger.path:
            raise HulkSmashLiveTelemetryError("telemetry ledger differs from config")
        credentials = wallet_configured and signing_key_configured
        if armed:
            config.require_live_start(credentials_present=credentials)
        elif config.mode != "observe":
            raise HulkSmashLiveTelemetryError(
                "disarmed telemetry requires explicit observe mode"
            )
        self._config = config
        self._ledger = ledger
        self._armed = armed
        self._wallet_configured = bool(wallet_configured)
        self._signing_key_configured = bool(signing_key_configured)
        self._now_fn = now_fn
        records = ledger.read_all()
        self._seen_fills = _existing_keys(records, "fill")
        self._seen_fees = _existing_keys(records, "fee")
        self._seen_funding = _existing_funding(records)
        self._owned_order_ids = _existing_owned_order_ids(records)
        self._metrics = HulkSmashExecutionMetrics(
            strategy_id=config.strategy_id,
            markout_horizon_ms=config.markout_horizon_ms,
            records=records,
            clock_ms=self._clock_ms,
            emit=self.emit,
            owns_order=lambda oid: oid in self._owned_order_ids,
        )

    def emit(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Append one authority-stamped event."""
        self._ledger.append(
            event_type=event_type,
            observed_at_utc=self._now_utc(),
            live_armed=self._armed,
            execution_authority=("hyperliquid_mainnet" if self._armed else "none"),
            payload=payload,
        )

    def emit_preflight(
        self,
        preflight: SolVenuePreflight,
        venue: SolReconciliationSnapshot,
    ) -> None:
        """Record strategy identity, venue precision, fees, and account truth."""
        self.emit("configuration_identity", self._configuration_identity())
        self.emit(
            "effective_mode",
            {
                "state": "LIVE ARMED" if self._armed else "DISARMED OBSERVER",
                "account_abstraction_mode": preflight.account_abstraction_mode,
                "venue_max_leverage": preflight.market.max_leverage,
                "size_step": preflight.size_step,
                "price_tick": preflight.price_tick,
            },
        )
        self.emit(
            "fee",
            {
                "source": "venue_fee_schedule",
                "maker_rate": preflight.fees.maker_rate,
                "taker_rate": preflight.fees.taker_rate,
                "funding_source": "venue_account_ledger",
            },
        )
        self.emit_reconciliation(venue)

    def emit_history(self, decision: HulkSmashLiveDecision) -> None:
        """Record warmup bars without granting historical execution authority."""
        payload = decision.as_payload()
        payload.update(
            {
                "entry_direction": None,
                "short_entry": False,
                "entry_allowed": False,
                "decision_action": "history_only",
            }
        )
        self.emit("regime_history", payload)

    def emit_history_batch(self, decisions: tuple[HulkSmashLiveDecision, ...]) -> None:
        """Record a bounded warmup set under history-only authority."""
        for decision in decisions:
            self.emit_history(decision)

    def emit_decision(self, decision: HulkSmashLiveDecision) -> None:
        """Record one newly available completed-bar strategy decision."""
        self.emit("regime_decision", decision.as_payload())

    def emit_book(self, book: SolBookSnapshot) -> None:
        """Record one public Hyperliquid L2 snapshot for the read-only TUI."""
        if book.ask_depth <= 0.0:
            raise HulkSmashLiveTelemetryError("book ask depth must be positive")
        observed = self._now()
        self.emit(
            "book_observation",
            {
                "source": "hyperliquid_mainnet_l2_rest",
                "exchange_ts_ms": book.exchange_timestamp_ms,
                "recv_ts_ms": int(observed.timestamp() * 1_000),
                "mid_px": book.mid_price,
                "spread_bps": book.spread_bps,
                "bid_depth_ratio": book.bid_depth / book.ask_depth,
                "opi": book.order_pressure,
                "bids": [
                    {"price": level.price, "size": level.size} for level in book.bids
                ],
                "asks": [
                    {"price": level.price, "size": level.size} for level in book.asks
                ],
            },
        )
        self._metrics.observe_book(book)

    def emit_market_snapshot(
        self,
        *,
        adapter: HulkSmashVenueProtocol,
        funding_start_ms: int,
        observed_at_ms: int,
    ) -> int:
        """Record exact funding updates and current L2, then advance the cursor."""
        self.emit_funding_payments(
            adapter.funding_payments(
                start_time_ms=funding_start_ms,
                end_time_ms=observed_at_ms,
            )
        )
        self.emit_book(adapter.book_snapshot(depth_levels=5))
        return observed_at_ms

    def emit_reconciliation(self, venue: SolReconciliationSnapshot) -> None:
        """Record venue-authoritative account, position, orders, fills, and liq price."""
        position = venue.position
        self.emit(
            "reconciliation",
            {
                "account_value_usd": venue.account.account_value_usd,
                "withdrawable_usd": venue.account.withdrawable_usd,
                "open_order_ids": [order.oid for order in venue.open_orders],
                "open_orders": [_order_payload(order) for order in venue.open_orders],
                "fill_ids": [fill.oid for fill in venue.fills],
                "fill_trade_ids": [fill_trade_id(fill) for fill in venue.fills],
                "owned_fill_ids": [
                    fill.oid
                    for fill in venue.fills
                    if fill.oid in self._owned_order_ids
                ],
                "unattributed_fill_ids": [
                    fill.oid
                    for fill in venue.fills
                    if fill.oid not in self._owned_order_ids
                ],
            },
        )
        self.emit(
            "position",
            {
                "size_signed": position.size_signed,
                "entry_price": position.entry_price,
                "margin_used_usd": position.margin_used_usd,
                "position_value_usd": position.position_value_usd,
                "unrealized_pnl_usd": position.unrealized_pnl_usd,
                "leverage_type": position.leverage_type,
                "leverage": position.leverage,
            },
        )
        self.emit("liquidation_price", {"value": position.liquidation_price})
        for fill in venue.fills:
            self._emit_fill(fill)
        self._metrics.observe_reconciliation(venue)

    def emit_funding_payments(self, payments: tuple[SolFundingPayment, ...]) -> None:
        """Record each exact venue funding payment once across restarts."""
        for payment in payments:
            key = (payment.transaction_hash, payment.timestamp_ms)
            if key in self._seen_funding:
                continue
            self.emit(
                "funding",
                {
                    "venue_timestamp_ms": payment.timestamp_ms,
                    "usdc_delta": payment.usdc_delta,
                    "position_size_signed": payment.position_size_signed,
                    "funding_rate": payment.funding_rate,
                    "transaction_hash": payment.transaction_hash,
                },
            )
            self._seen_funding.add(key)

    def emit_ack(
        self,
        operation: str,
        ack: HyperliquidOrderAck,
        *,
        event_type: str = "order_acknowledgement",
    ) -> None:
        """Record one normalized venue acknowledgement."""
        latency = self._metrics.acknowledgement_payload(ack)
        self.emit(
            event_type,
            {
                "operation": operation,
                "accepted": ack.accepted,
                "oid": ack.oid,
                "status": ack.status,
                "filled_size": ack.filled_size,
                "average_price": ack.average_price,
                "error": ack.error,
                "client_order_id": ack.client_order_id,
                "recovered_after_transport_error": ack.recovered_after_transport_error,
                "venue_timestamp_ms": ack.venue_timestamp_ms,
                "recovered_after_restart": ack.recovered_after_restart,
                **latency,
            },
        )
        if ack.accepted and ack.oid is not None:
            self.claim_order_ids((ack.oid,))

    def emit_order_intent(self, **payload: object) -> None:
        """Persist one order intent and start its local latency clock."""
        started_at_ms = self._clock_ms()
        self.emit("order_intent", payload)
        self._metrics.record_order_intent(payload, started_at_ms=started_at_ms)

    def emit_cancel_intent(self, *, operation: str, oid: int) -> None:
        """Persist one exact cancellation intent and start its latency clock."""
        started_at_ms = self._clock_ms()
        self.emit("cancel_intent", {"operation": operation, "oid": oid})
        self._metrics.record_cancel_intent(oid, started_at_ms=started_at_ms)

    def claim_order_ids(self, order_ids: tuple[int, ...]) -> None:
        """Register exact strategy-owned venue IDs for fill attribution."""
        for oid in order_ids:
            if isinstance(oid, bool) or not isinstance(oid, int) or oid <= 0:
                raise HulkSmashLiveTelemetryError(
                    "owned order IDs must be positive integers"
                )
            self._owned_order_ids.add(oid)

    def emit_state(self, payload: Mapping[str, object]) -> None:
        """Record a complete recoverable lifecycle projection."""
        self.emit("state_transition", payload)

    def emit_protection_plan(self, payload: Mapping[str, object]) -> None:
        """Record stop and target calculations before order submission."""
        self.emit("protective_stop_plan", payload)

    def emit_close(self, payload: Mapping[str, object]) -> None:
        """Record an exit intent or venue-verified flat completion."""
        self.emit("close", payload)

    def emit_fault(self, reason: str) -> None:
        """Record a non-empty backend fault without success-shaped fallback."""
        message = reason.strip()
        if not message:
            raise HulkSmashLiveTelemetryError("fault reason must be non-empty")
        self.emit("fault", {"reason": message})

    def _configuration_identity(self) -> dict[str, object]:
        config = self._config
        return {
            "symbol": config.symbol,
            "strategy_name": config.strategy_id,
            "capital_source": config.capital_source,
            "portfolio_purpose": config.portfolio_purpose,
            "backend_ledger_path": str(config.backend_ledger),
            "metalabel_mode": config.metalabel_mode,
            "metalabel_policy": {
                "observation_type": "annotation_collection",
                "inference_active": False,
                "may_filter": False,
                "may_scale": False,
                "execution_authority": "none",
            },
            "wallet_configured": self._wallet_configured,
            "signing_key_configured": self._signing_key_configured,
            "strategy_params": _strategy_params(config),
            "position_policy": {
                "position_mode": "isolated_one_way",
                "max_positions_per_symbol": config.max_positions_per_symbol,
            },
            "risk": _risk(config),
            "regime_policy": _signal_policy(config),
            "exits": _exits(config),
            "execution": _execution(config),
            "costs": {"funding_source": "venue_account_ledger"},
            "runtime": {
                "lookback_days": config.lookback_days,
                "purpose": config.portfolio_purpose,
                "offline_edge_status": "forward_robustness_survivor_not_live_proven",
            },
        }

    def _emit_fill(self, fill: SolFill) -> None:
        key = fill_trade_id(fill)
        if fill.oid not in self._owned_order_ids:
            self._seen_fills.add(key)
            self._seen_fees.add(key)
            return
        if key not in self._seen_fills:
            self.emit("fill", _fill_payload(fill))
            self._seen_fills.add(key)
        if key not in self._seen_fees:
            self.emit(
                "fee",
                {
                    "source": "fill",
                    "oid": fill.oid,
                    "trade_id": fill.trade_id,
                    "venue_timestamp_ms": fill.timestamp_ms,
                    "fee_usd": fill.fee_usd,
                    "fee_token": fill.fee_token,
                },
            )
            self._seen_fees.add(key)

    def _now(self) -> datetime:
        value = self._now_fn()
        if value.tzinfo is None or value.utcoffset() is None:
            raise HulkSmashLiveTelemetryError("now_fn must return an aware datetime")
        return value.astimezone(timezone.utc)

    def _now_utc(self) -> str:
        return self._now().isoformat()

    def _clock_ms(self) -> int:
        return int(self._now().timestamp() * 1_000)


def _strategy_params(config: HulkSmashLiveConfig) -> dict[str, object]:
    return {
        "leverage": config.leverage,
        "minimum_score": config.minimum_score,
        "pivot_bars": config.pivot_bars,
        "supertrend_period": config.supertrend_period,
        "supertrend_multiplier": config.supertrend_multiplier,
        "adx_period": config.adx_period,
        "squeeze_period": config.squeeze_period,
        "adx_usable": config.adx_usable,
        "adx_trending": config.adx_trending,
    }


def _risk(config: HulkSmashLiveConfig) -> dict[str, object]:
    return {
        "risk_fraction": config.risk_fraction,
        "maximum_portfolio_risk_fraction": config.maximum_portfolio_risk_fraction,
        "max_notional_usd": config.max_notional_usd,
    }


def _signal_policy(config: HulkSmashLiveConfig) -> dict[str, object]:
    return {
        "engine": "hulk_smash_completed_bar_score_v3",
        "classification": "NOT_A_REGIME_CLASSIFIER",
        "signal_timeframe": config.signal_timeframe,
        "execution_timeframe": "next_30m_bar",
        "side": "short_only",
        "completed_bars_only": True,
    }


def _exits(config: HulkSmashLiveConfig) -> dict[str, object]:
    return {
        "stop_anchor": "prior_6_bar_structural_pivot_clamped",
        "minimum_stop_bps": config.minimum_stop_bps,
        "maximum_stop_bps": config.maximum_stop_bps,
        "target_r_multiple": config.target_r_multiple,
        "maximum_hold_bars": config.maximum_hold_bars,
    }


def _execution(config: HulkSmashLiveConfig) -> dict[str, object]:
    return {
        "entry_order_type": "market",
        "protective_stop_order_type": "reduce_only_stop_market",
        "target_order_type": "reduce_only_limit",
        "maximum_hold_exit": "reduce_only_market",
        "market_slippage_cap_fraction": config.market_slippage_cap_fraction,
        "maximum_entry_delay_seconds": config.maximum_entry_delay_seconds,
        "markout_horizon_ms": config.markout_horizon_ms,
        "fill_identity": "hyperliquid_tid",
    }


def _order_payload(order: SolOpenOrder) -> dict[str, object]:
    return {
        "oid": order.oid,
        "size": order.size,
        "side": order.side,
        "reduce_only": order.reduce_only,
        "is_trigger": order.is_trigger,
        "trigger_price": order.trigger_price,
        "limit_price": order.limit_price,
        "order_type": order.order_type,
    }


def _fill_payload(fill: SolFill) -> dict[str, object]:
    return {
        "oid": fill.oid,
        "trade_id": fill.trade_id,
        "venue_timestamp_ms": fill.timestamp_ms,
        "price": fill.price,
        "size": fill.size,
        "side": fill.side,
        "direction": fill.direction,
        "closed_pnl_usd": fill.closed_pnl_usd,
        "crossed": fill.crossed,
        "transaction_hash": fill.transaction_hash,
        "fee_usd": fill.fee_usd,
        "fee_token": fill.fee_token,
    }


def _existing_keys(records: list[dict[str, object]], event_type: str) -> set[int]:
    keys: set[int] = set()
    for record in records:
        if record.get("event_type") != event_type:
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if event_type == "fee" and payload.get("source") != "fill":
            continue
        keys.add(ledger_trade_id(payload, label=f"{event_type} trade_id"))
    return keys


def _existing_funding(records: list[dict[str, object]]) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for record in records:
        if record.get("event_type") != "funding":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        transaction = payload.get("transaction_hash")
        timestamp = payload.get("venue_timestamp_ms")
        if isinstance(transaction, str) and isinstance(timestamp, int):
            keys.add((transaction, timestamp))
    return keys


def _existing_owned_order_ids(records: list[dict[str, object]]) -> set[int]:
    order_ids: set[int] = set()
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("accepted") is not True:
            continue
        oid = payload.get("oid")
        if isinstance(oid, int) and not isinstance(oid, bool) and oid > 0:
            order_ids.add(oid)
    return order_ids
