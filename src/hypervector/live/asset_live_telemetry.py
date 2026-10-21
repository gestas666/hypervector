"""Authoritative live-ledger projection for per-asset execution lifecycle facts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from hypervector.live.hyperliquid_fill_identity import fill_trade_id, ledger_trade_id
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidBookSnapshot,
    HyperliquidFill,
    HyperliquidFundingPayment,
    HyperliquidOpenOrder,
    HyperliquidReconciliationSnapshot,
    HyperliquidVenuePreflight,
)
from hypervector.live.multi_asset_preflight_fees import preflight_fee_payload
from hypervector.live.asset_engine_config import AssetEngineConfig
from hypervector.live.asset_ledger import AssetLiveLedger
from hypervector.live.asset_state import AssetLiveSnapshot

_RECOVERY_EVENT_TYPES = frozenset({"fill", "fee", "funding"})


class AssetLiveTelemetryError(RuntimeError):
    """Live telemetry cannot produce a valid authoritative record."""


class AssetLiveTelemetry:
    """Render execution facts into the append-only per-asset live ledger."""

    def __init__(
        self,
        *,
        config: AssetEngineConfig,
        ledger: AssetLiveLedger,
        now_fn: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._ledger = ledger
        self._now_fn = now_fn
        existing = ledger.read_matching(
            lambda row: row.get("sequence") == 1
            or row.get("event_type") in _RECOVERY_EVENT_TYPES,
            event_types=_RECOVERY_EVENT_TYPES,
        )
        self._fresh_ledger = not existing
        self._run_started_at_ms = _ledger_started_at_ms(existing)
        self._seen_fills = _existing_fill_keys(existing, "fill")
        self._seen_fill_fees = _existing_fill_keys(existing, "fee")
        self._seen_funding = _existing_funding_keys(existing)

    def emit(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Append one armed-mainnet backend event without secrets."""
        self._ledger.append(
            event_type=event_type,
            observed_at_utc=self._now_utc(),
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload=payload,
        )

    def emit_preflight(
        self,
        preflight: HyperliquidVenuePreflight,
        venue: HyperliquidReconciliationSnapshot,
    ) -> None:
        """Record frozen profile, venue precision, fees, and account state."""
        if self._fresh_ledger:
            self._baseline_existing_fills(venue.fills)
            self._fresh_ledger = False
        self.emit(
            "configuration_identity",
            self._configuration_identity(),
        )
        self.emit(
            "effective_mode",
            {
                "state": "LIVE ARMED",
                "account_abstraction_mode": preflight.account_abstraction_mode,
                "venue_max_leverage": preflight.market.max_leverage,
                "size_step": preflight.size_step,
                "price_tick": preflight.price_tick,
            },
        )
        self.emit(
            "fee",
            _fee_event_payload(self._config.symbol, preflight),
        )
        self.emit_reconciliation(venue)

    def _baseline_existing_fills(self, fills: tuple[HyperliquidFill, ...]) -> None:
        for fill in fills:
            if not isinstance(fill, HyperliquidFill):
                raise AssetLiveTelemetryError("reconciliation fill has an invalid type")
            key = fill_trade_id(fill)
            self._seen_fills.add(key)
            self._seen_fill_fees.add(key)

    def _configuration_identity(self) -> dict[str, object]:
        return {
            "symbol": self._config.symbol,
            "strategy_name": self._config.strategy_id,
            "capital_source": self._config.capital_source,
            "portfolio_purpose": self._config.portfolio_purpose,
            "backend_ledger_path": str(self._config.live_ledger),
            "metalabel_mode": self._config.metalabel_mode,
            "wallet_configured": True,
            "signing_key_configured": True,
            "strategy_params": {"leverage": self._config.leverage},
            "position_policy": {
                "position_mode": f"{self._config.margin_mode}_one_way",
                "max_positions_per_symbol": self._config.max_positions_per_symbol,
            },
            "risk": {
                "margin_fraction": self._config.margin_fraction,
                "max_notional_usd": self._config.max_notional_usd,
            },
            "exits": {
                "stop_bps": self._config.stop_bps,
                "maximum_hold_seconds": self._config.maximum_hold_seconds,
            },
            "execution": {
                "order_type": "market",
                "time_in_force": "ioc",
                "fill_identity": "hyperliquid_tid",
                "market_slippage_cap_fraction": (self._config.market_slippage_cap_fraction),
            },
        }

    def emit_reconciliation(self, venue: HyperliquidReconciliationSnapshot) -> None:
        """Record clearinghouse exposure, orders, fills, and liquidation price."""
        position = venue.position
        self.emit(
            "reconciliation",
            {
                "account_value_usd": venue.account.account_value_usd,
                "withdrawable_usd": venue.account.withdrawable_usd,
                "open_order_ids": [order.oid for order in venue.open_orders],
                "open_orders": [_open_order_payload(order) for order in venue.open_orders],
                "fill_ids": [fill.oid for fill in venue.fills],
                "fill_trade_ids": [fill_trade_id(fill) for fill in venue.fills],
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

    def emit_book(self, book: HyperliquidBookSnapshot) -> None:
        """Record a read-only venue L2 snapshot for the TUI depth ladder."""
        if book.ask_depth <= 0.0:
            raise AssetLiveTelemetryError("book ask depth must be positive")
        observed = self._now_fn()
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise AssetLiveTelemetryError("now_fn must return a timezone-aware datetime")
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
                "bids": [{"price": level.price, "size": level.size} for level in book.bids],
                "asks": [{"price": level.price, "size": level.size} for level in book.asks],
            },
        )

    def _emit_fill(self, fill: object) -> None:
        if not isinstance(fill, HyperliquidFill):
            raise AssetLiveTelemetryError("reconciliation fill has an invalid type")
        key = fill_trade_id(fill)
        if self._run_started_at_ms is not None and fill.timestamp_ms < self._run_started_at_ms:
            self._seen_fills.add(key)
            self._seen_fill_fees.add(key)
            return
        if key not in self._seen_fills:
            self.emit(
                "fill",
                {
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
                },
            )
            self._seen_fills.add(key)
        if key not in self._seen_fill_fees:
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
            self._seen_fill_fees.add(key)

    def emit_ack(
        self,
        operation: str,
        ack: HyperliquidOrderAck,
        *,
        event_type: str = "order_acknowledgement",
        extra_payload: Mapping[str, object] | None = None,
    ) -> None:
        """Record one normalized exchange acknowledgement."""
        self.emit(event_type, order_ack_payload(operation, ack, extra_payload))

    def emit_funding_payments(
        self,
        payments: tuple[HyperliquidFundingPayment, ...],
    ) -> None:
        """Record each exact user-funding ledger update once across restarts."""
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

    def emit_state(self, snapshot: AssetLiveSnapshot) -> None:
        """Record the complete recoverable lifecycle identity."""
        self.emit("state_transition", snapshot.as_payload())

    def _now_utc(self) -> str:
        value = self._now_fn()
        if value.tzinfo is None or value.utcoffset() is None:
            raise AssetLiveTelemetryError("now_fn must return a timezone-aware datetime")
        return value.astimezone(timezone.utc).isoformat()


def order_ack_payload(
    operation: str,
    ack: HyperliquidOrderAck,
    extra_payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the exact journaled payload of one normalized acknowledgement."""
    payload: dict[str, object] = {
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
    }
    if extra_payload is not None:
        payload.update(extra_payload)
    return payload


def _fee_event_payload(
    symbol: str,
    preflight: HyperliquidVenuePreflight,
) -> dict[str, object]:
    evidence = preflight_fee_payload(
        symbol=symbol,
        fees=preflight.fees,
        hip3_metadata=preflight.hip3_fee_metadata,
    )
    return {
        **evidence,
        "source": (
            "unresolved_hip3_fee_schedule"
            if evidence["effective_fee_status"] == "unresolved_deployer_fee_scale"
            else "effective_hip3_fee_schedule"
            if preflight.hip3_fee_metadata is not None
            else "venue_fee_schedule"
        ),
        "maker_rate": evidence["effective_maker_fee_rate"],
        "taker_rate": evidence["effective_taker_fee_rate"],
    }


def _existing_fill_keys(
    records: list[dict[str, object]],
    event_type: str,
) -> set[int]:
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


def _ledger_started_at_ms(records: list[dict[str, object]]) -> int | None:
    if not records:
        return None
    value = records[0].get("observed_at_utc")
    if not isinstance(value, str):
        raise AssetLiveTelemetryError("existing live ledger lacks a start timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AssetLiveTelemetryError("existing live ledger start must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def _open_order_payload(order: HyperliquidOpenOrder) -> dict[str, object]:
    payload: dict[str, object] = {
        "oid": order.oid,
        "size": order.size,
        "side": order.side,
        "reduce_only": order.reduce_only,
        "is_trigger": order.is_trigger,
        "trigger_price": order.trigger_price,
        "order_type": order.order_type,
    }
    if order.limit_price is not None:
        payload["limit_price"] = order.limit_price
    return payload


def _existing_funding_keys(
    records: list[dict[str, object]],
) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for record in records:
        if record.get("event_type") != "funding":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        transaction_hash = payload.get("transaction_hash")
        timestamp = payload.get("venue_timestamp_ms")
        if isinstance(transaction_hash, str) and isinstance(timestamp, int):
            keys.add((transaction_hash, timestamp))
    return keys
