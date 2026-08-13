"""Backend-authoritative telemetry for the Apex MM measurement canary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from hypervector.live.apex_mm_live_config import ApexMMLiveConfig
from hypervector.live.apex_mm_live_ledger import ApexMMLiveLedger
from hypervector.live.apex_mm_live_models import ApexMMLiveSnapshot
from hypervector.live.hyperliquid_fill_identity import fill_trade_id, ledger_trade_id
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolBookSnapshot,
    SolFill,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.sol_range_onset_live_telemetry import (
    SolLiveTelemetry,
    SolLiveTelemetryError,
)
from hypervector.research.apex_regime_mm_policy import ApexMMQuote


class ApexMMLiveTelemetry(SolLiveTelemetry):
    """Project paired quotes, venue facts, and fill markouts to one ledger."""

    def __init__(
        self,
        *,
        config: ApexMMLiveConfig,
        ledger: ApexMMLiveLedger,
        now_fn: Callable[[], datetime],
    ) -> None:
        super().__init__(config=config, ledger=ledger, now_fn=now_fn)  # type: ignore[arg-type]
        self._mm_config = config
        self._markouts_active = False
        existing = ledger.read_all()
        self._seen_markout_fills = _existing_event_keys(existing, "fill_markout")
        self._seen_quality_fills = _existing_event_keys(existing, "execution_quality")
        self._pending_markouts: dict[int, SolFill] = {}
        self._latest_quote_prices: dict[str, float] = {}
        self._quote_prices_by_oid: dict[int, float] = {}
        self._intent_started_by_client: dict[str, int] = {}
        self._intent_started_by_oid: dict[int, int] = {}
        self._intent_prices_by_client: dict[str, float] = {}
        self._latest_position: SolPositionSnapshot | None = None
        self._mm_run_started_at_ms: int | None = None

    def emit_preflight(
        self,
        preflight: SolVenuePreflight,
        venue: SolReconciliationSnapshot,
    ) -> None:
        """Emit venue identity while baselining pre-run fills for markouts."""
        self._mm_run_started_at_ms = self._clock_ms()
        self._markouts_active = False
        super().emit_preflight(preflight, venue)
        self._seen_markout_fills.update(fill_trade_id(fill) for fill in venue.fills)
        self._seen_quality_fills.update(fill_trade_id(fill) for fill in venue.fills)
        self._markouts_active = True

    def _configuration_identity(self) -> dict[str, object]:
        config = self._mm_config
        return {
            "symbol": config.symbol,
            "strategy_name": config.strategy_id,
            "capital_source": config.capital_source,
            "portfolio_purpose": config.portfolio_purpose,
            "backend_ledger_path": str(config.backend_ledger),
            "metalabel_mode": "disabled",
            "wallet_configured": True,
            "signing_key_configured": True,
            "strategy_params": {
                "leverage": config.leverage,
                "base_order_notional_usd": config.base_order_notional_usd,
            },
            "position_policy": {
                "position_mode": "isolated_one_way_net_inventory",
                "max_positions_per_symbol": config.max_positions_per_symbol,
            },
            "risk": {
                "max_inventory_notional_usd": config.max_inventory_notional_usd,
                "maximum_reserved_margin_usd": (
                    config.max_inventory_notional_usd / config.leverage
                ),
            },
            "execution": {
                "order_type": "paired_post_only_limit",
                "submission_transport": "single_bulk_orders_action",
                "minimum_order_notional_usd": config.minimum_order_notional_usd,
                "quote_refresh_ms": config.quote_refresh_ms,
                "maximum_book_age_ms": config.maximum_book_age_ms,
                "markout_horizon_ms": config.markout_horizon_ms,
                "fill_identity": "hyperliquid_tid",
                "depth_levels": config.depth_levels,
                "stop_behavior": "cancel_all_then_taker_flatten_verify_flat",
            },
            "regime_policy": {
                "engine": "not_used_for_market_maker_entries",
                "classification": "NOT_CLASSIFIED",
            },
            "runtime": {
                "purpose": "execution_friction_measurement",
                "offline_edge_status": "not_demonstrated",
            },
        }

    def emit_reconciliation(self, venue: SolReconciliationSnapshot) -> None:
        """Emit venue truth and retain only newly observed fills for markout."""
        super().emit_reconciliation(venue)
        self._latest_position = venue.position
        if not self._markouts_active:
            return
        for fill in venue.fills:
            key = fill_trade_id(fill)
            if (
                self._mm_run_started_at_ms is not None
                and fill.timestamp_ms < self._mm_run_started_at_ms
            ):
                self._seen_markout_fills.add(key)
                self._seen_quality_fills.add(key)
                continue
            self._emit_execution_quality_once(fill, key)
            if key in self._seen_markout_fills:
                continue
            self._seen_markout_fills.add(key)
            self._pending_markouts[key] = fill

    def emit_book(self, book: SolBookSnapshot) -> None:
        """Emit L2 truth and complete due fill markouts from its midpoint."""
        super().emit_book(book)
        self._emit_liquidation_distance(book)
        due = [
            key
            for key, fill in self._pending_markouts.items()
            if book.exchange_timestamp_ms
            >= fill.timestamp_ms + self._mm_config.markout_horizon_ms
        ]
        for key in due:
            fill = self._pending_markouts.pop(key)
            self._emit_markout(fill, book)

    def emit_quote(
        self,
        quote: ApexMMQuote,
        inventory_notional_usd: float,
    ) -> None:
        """Record the exact pure-policy quote before any venue mutation."""
        self._latest_quote_prices = _quote_prices(quote)
        self.emit(
            "theoretical_quote",
            {
                "strategy_id": self._mm_config.strategy_id,
                "active": quote.active,
                "reason": quote.reason,
                "fair_value": quote.fair_value,
                "bid_price": quote.bid_price,
                "ask_price": quote.ask_price,
                "bid_size": quote.bid_size,
                "ask_size": quote.ask_size,
                "full_spread_bps": quote.full_spread_bps,
                "inventory_utilization": quote.inventory_utilization,
                "inventory_notional_usd": inventory_notional_usd,
            },
        )

    def emit_order_intent(self, **payload: object) -> None:
        """Record one secret-free quote or cancellation intent."""
        self.emit(
            "order_intent",
            {"strategy_id": self._mm_config.strategy_id, **payload},
        )
        started_at_ms = self._clock_ms()
        client_order_id = payload.get("client_order_id")
        oid = payload.get("oid")
        if isinstance(client_order_id, str):
            self._intent_started_by_client[client_order_id] = started_at_ms
            limit_price = payload.get("limit_price")
            if (
                isinstance(limit_price, (int, float))
                and not isinstance(limit_price, bool)
                and limit_price > 0.0
            ):
                self._intent_prices_by_client[client_order_id] = float(limit_price)
        if isinstance(oid, int) and not isinstance(oid, bool):
            self._intent_started_by_oid[oid] = started_at_ms

    def emit_ack(
        self,
        operation: str,
        ack: HyperliquidOrderAck,
        *,
        event_type: str = "order_acknowledgement",
    ) -> None:
        """Record an acknowledgement and bind its venue order to its quote."""
        latency_ms = self._ack_latency_ms(ack)
        extra = {"round_trip_latency_ms": latency_ms}
        super().emit_ack(
            operation,
            ack,
            event_type=event_type,
            extra_payload=extra,
        )
        price = (
            self._intent_prices_by_client.pop(ack.client_order_id, None)
            if ack.client_order_id is not None
            else None
        )
        if price is None:
            price = self._latest_quote_prices.get(operation.removeprefix("quote_"))
        if ack.accepted and ack.oid is not None and price is not None:
            self._quote_prices_by_oid[ack.oid] = price

    def emit_state(self, snapshot: ApexMMLiveSnapshot) -> None:
        """Record paired order identities and reconciled net inventory."""
        self._bind_quote_oid(snapshot.bid_oid, "buy")
        self._bind_quote_oid(snapshot.ask_oid, "sell")
        self.emit(
            "state_transition",
            {
                "strategy_id": self._mm_config.strategy_id,
                "state": snapshot.state.value,
                "bid_oid": snapshot.bid_oid,
                "ask_oid": snapshot.ask_oid,
                "position_size_signed": snapshot.position_size_signed,
                "quote_started_at_ms": snapshot.quote_started_at_ms,
                "last_fault": snapshot.last_fault,
            },
        )

    def emit_fault(self, message: str) -> None:
        """Record one fail-closed lifecycle fault without execution fallback."""
        self.emit(
            "fault",
            {"strategy_id": self._mm_config.strategy_id, "message": message},
        )

    def _emit_markout(self, fill: SolFill, book: SolBookSnapshot) -> None:
        sign = _fill_sign(fill)
        markout = sign * (book.mid_price / fill.price - 1.0) * 10_000.0
        self.emit(
            "fill_markout",
            {
                "strategy_id": self._mm_config.strategy_id,
                "oid": fill.oid,
                "trade_id": fill.trade_id,
                "fill_timestamp_ms": fill.timestamp_ms,
                "fill_price": fill.price,
                "fill_size": fill.size,
                "fill_side": fill.side,
                "liquidity_side": "taker" if fill.crossed else "maker",
                "mark_timestamp_ms": book.exchange_timestamp_ms,
                "mark_price": book.mid_price,
                "horizon_ms": book.exchange_timestamp_ms - fill.timestamp_ms,
                "markout_bps": round(markout, 10),
            },
        )

    def _bind_quote_oid(self, oid: int | None, side: str) -> None:
        price = self._latest_quote_prices.get(side)
        if oid is not None and price is not None:
            self._quote_prices_by_oid.setdefault(oid, price)

    def _clock_ms(self) -> int:
        value = self._now_fn()
        if value.tzinfo is None or value.utcoffset() is None:
            raise SolLiveTelemetryError("now_fn must return a timezone-aware datetime")
        return int(value.timestamp() * 1_000)

    def _ack_latency_ms(self, ack: HyperliquidOrderAck) -> int | None:
        started_at_ms = None
        if ack.client_order_id is not None:
            started_at_ms = self._intent_started_by_client.pop(
                ack.client_order_id,
                None,
            )
        if started_at_ms is None and ack.oid is not None:
            started_at_ms = self._intent_started_by_oid.pop(ack.oid, None)
        if started_at_ms is None:
            return None
        latency_ms = self._clock_ms() - started_at_ms
        if latency_ms < 0:
            raise SolLiveTelemetryError("acknowledgement clock preceded its intent")
        return latency_ms

    def _emit_execution_quality_once(
        self,
        fill: SolFill,
        key: int,
    ) -> None:
        if key in self._seen_quality_fills:
            return
        expected = self._quote_prices_by_oid.get(fill.oid)
        if expected is None:
            return
        slippage = _fill_sign(fill) * (fill.price / expected - 1.0) * 10_000.0
        self.emit(
            "execution_quality",
            {
                "strategy_id": self._mm_config.strategy_id,
                "oid": fill.oid,
                "trade_id": fill.trade_id,
                "fill_timestamp_ms": fill.timestamp_ms,
                "expected_quote_price": expected,
                "fill_price": fill.price,
                "fill_size": fill.size,
                "fill_side": fill.side,
                "liquidity_side": "taker" if fill.crossed else "maker",
                "slippage_bps": round(slippage, 10),
            },
        )
        self._seen_quality_fills.add(key)

    def _emit_liquidation_distance(self, book: SolBookSnapshot) -> None:
        position = self._latest_position
        if position is None or position.size_signed == 0.0:
            return
        liquidation = position.liquidation_price
        if liquidation is None:
            return
        sign = 1.0 if position.size_signed > 0.0 else -1.0
        distance = sign * (book.mid_price - liquidation) / book.mid_price * 100.0
        self.emit(
            "liquidation_distance",
            {
                "strategy_id": self._mm_config.strategy_id,
                "side": "long" if sign > 0.0 else "short",
                "mark_price": book.mid_price,
                "liquidation_price": liquidation,
                "distance_pct": round(distance, 10),
                "liquidatable": distance <= 0.0,
            },
        )


def _fill_sign(fill: SolFill) -> float:
    side = fill.side.strip().upper()
    if side in {"B", "BUY"}:
        return 1.0
    if side in {"A", "S", "SELL"}:
        return -1.0
    raise ValueError(f"unsupported Hyperliquid fill side for markout: {fill.side!r}")


def _quote_prices(quote: ApexMMQuote) -> dict[str, float]:
    prices: dict[str, float] = {}
    if quote.bid_price is not None:
        prices["buy"] = quote.bid_price
    if quote.ask_price is not None:
        prices["sell"] = quote.ask_price
    return prices


def _existing_event_keys(
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
        keys.add(ledger_trade_id(payload, label=f"{event_type} trade_id"))
    return keys
