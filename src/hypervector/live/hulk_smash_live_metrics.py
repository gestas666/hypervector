"""Restart-safe execution-quality measurements for the Hulk canary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolBookSnapshot,
    SolFill,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
)
from hypervector.live.hyperliquid_fill_identity import fill_trade_id, ledger_trade_id

MetricEmitter = Callable[[str, Mapping[str, object]], None]


class HulkSmashExecutionMetrics:
    """Track latency, slippage, markout, and liquidation distance durably."""

    def __init__(
        self,
        *,
        strategy_id: str,
        markout_horizon_ms: int,
        records: list[dict[str, object]],
        clock_ms: Callable[[], int],
        emit: MetricEmitter,
        owns_order: Callable[[int], bool],
    ) -> None:
        self._strategy_id = strategy_id
        self._markout_horizon_ms = markout_horizon_ms
        self._clock_ms = clock_ms
        self._emit = emit
        self._owns_order = owns_order
        self._intent_started_by_client: dict[str, int] = {}
        self._cancel_started_by_oid: dict[int, int] = {}
        self._expected_by_client: dict[str, float] = {}
        self._expected_by_oid: dict[int, float] = {}
        self._seen_quality = _event_keys(records, "execution_quality")
        self._seen_markouts = _event_keys(records, "fill_markout")
        self._pending_quality: dict[int, SolFill] = {}
        self._pending_markouts: dict[int, SolFill] = {}
        self._restored_markouts: set[int] = set()
        self._latest_position: SolPositionSnapshot | None = None
        self._restore(records)

    def record_order_intent(
        self,
        payload: Mapping[str, object],
        *,
        started_at_ms: int,
    ) -> None:
        """Retain local start time and expected price for one submitted order."""
        client_order_id = payload.get("client_order_id")
        if not isinstance(client_order_id, str) or not client_order_id:
            raise ValueError("Hulk order intent requires client_order_id")
        self._intent_started_by_client[client_order_id] = started_at_ms
        expected = _expected_price(payload)
        if expected is not None:
            self._expected_by_client[client_order_id] = expected

    def record_cancel_intent(self, oid: int, *, started_at_ms: int) -> None:
        """Retain the local start time for one exact cancellation."""
        if isinstance(oid, bool) or not isinstance(oid, int) or oid <= 0:
            raise ValueError("Hulk cancel intent requires a positive OID")
        self._cancel_started_by_oid[oid] = started_at_ms

    def acknowledgement_payload(self, ack: HyperliquidOrderAck) -> dict[str, object]:
        """Bind an acknowledgement to its intent and return latency evidence."""
        started_at_ms = self._pop_intent_start(ack)
        latency_ms = None if started_at_ms is None else self._clock_ms() - started_at_ms
        if latency_ms is not None and latency_ms < 0:
            raise ValueError("Hulk acknowledgement clock preceded its intent")
        expected = self._pop_expected_price(ack.client_order_id)
        if ack.accepted and ack.oid is not None and expected is not None:
            self._expected_by_oid[ack.oid] = expected
        return {"round_trip_latency_ms": latency_ms}

    def observe_reconciliation(self, venue: SolReconciliationSnapshot) -> None:
        """Update position truth and emit owned-fill quality exactly once."""
        self._latest_position = venue.position
        for fill in venue.fills:
            if not self._owns_order(fill.oid):
                continue
            key = fill_trade_id(fill)
            self._emit_quality_once(fill, key)
            if key not in self._seen_markouts:
                self._pending_markouts[key] = fill

    def observe_book(self, book: SolBookSnapshot) -> None:
        """Complete due markouts and project liquidation distance from venue facts."""
        self._emit_liquidation_distance(book)
        for key, fill in tuple(self._pending_quality.items()):
            self._emit_quality_once(fill, key)
        due = [
            key
            for key, fill in self._pending_markouts.items()
            if book.exchange_timestamp_ms
            >= fill.timestamp_ms + self._markout_horizon_ms
        ]
        for key in due:
            fill = self._pending_markouts.pop(key)
            self._emit_markout(
                fill,
                book,
                recovered_after_restart=key in self._restored_markouts,
            )
            self._restored_markouts.discard(key)
            self._seen_markouts.add(key)

    def _restore(self, records: list[dict[str, object]]) -> None:
        for record in records:
            event_type = record.get("event_type")
            payload = record.get("payload")
            if not isinstance(event_type, str) or not isinstance(payload, dict):
                continue
            if event_type == "order_intent":
                self._restore_order_intent(record, payload)
            elif event_type == "cancel_intent":
                self._restore_cancel_intent(record, payload)
            elif _is_ack_payload(payload):
                self._restore_ack(payload)
            elif event_type == "fill":
                self._restore_fill(payload)

    def _restore_order_intent(
        self,
        record: Mapping[str, object],
        payload: Mapping[str, object],
    ) -> None:
        identity = payload.get("client_order_id")
        timestamp_ms = _record_timestamp_ms(record)
        if isinstance(identity, str) and timestamp_ms is not None:
            self._intent_started_by_client[identity] = timestamp_ms
            expected = _expected_price(payload)
            if expected is not None:
                self._expected_by_client[identity] = expected

    def _restore_cancel_intent(
        self,
        record: Mapping[str, object],
        payload: Mapping[str, object],
    ) -> None:
        oid = payload.get("oid")
        timestamp_ms = _record_timestamp_ms(record)
        if _positive_int(oid) and timestamp_ms is not None:
            self._cancel_started_by_oid[oid] = timestamp_ms

    def _restore_ack(self, payload: Mapping[str, object]) -> None:
        identity = payload.get("client_order_id")
        oid = payload.get("oid")
        expected = self._pop_expected_price(
            identity if isinstance(identity, str) else None
        )
        if isinstance(identity, str):
            self._intent_started_by_client.pop(identity, None)
        if _positive_int(oid):
            self._cancel_started_by_oid.pop(oid, None)
            if payload.get("accepted") is True and expected is not None:
                self._expected_by_oid[oid] = expected

    def _restore_fill(self, payload: Mapping[str, object]) -> None:
        fill = _fill_from_payload(payload)
        if fill is None:
            return
        key = fill_trade_id(fill)
        if key not in self._seen_quality:
            self._pending_quality[key] = fill
        if key not in self._seen_markouts:
            self._pending_markouts[key] = fill
            self._restored_markouts.add(key)

    def _pop_intent_start(self, ack: HyperliquidOrderAck) -> int | None:
        if ack.client_order_id is not None:
            started = self._intent_started_by_client.pop(ack.client_order_id, None)
            if started is not None:
                return started
        if ack.oid is not None:
            return self._cancel_started_by_oid.pop(ack.oid, None)
        return None

    def _pop_expected_price(self, client_order_id: str | None) -> float | None:
        if client_order_id is None:
            return None
        return self._expected_by_client.pop(client_order_id, None)

    def _emit_quality_once(self, fill: SolFill, key: int) -> None:
        if key in self._seen_quality:
            self._pending_quality.pop(key, None)
            return
        expected = self._expected_by_oid.get(fill.oid)
        if expected is None:
            return
        slippage = _fill_sign(fill) * (fill.price / expected - 1.0) * 10_000.0
        self._emit(
            "execution_quality",
            _quality_payload(self._strategy_id, fill, expected, slippage),
        )
        self._seen_quality.add(key)
        self._pending_quality.pop(key, None)

    def _emit_markout(
        self,
        fill: SolFill,
        book: SolBookSnapshot,
        *,
        recovered_after_restart: bool,
    ) -> None:
        horizon_ms = book.exchange_timestamp_ms - fill.timestamp_ms
        markout = _fill_sign(fill) * (book.mid_price / fill.price - 1.0) * 10_000.0
        self._emit(
            "fill_markout",
            {
                "strategy_id": self._strategy_id,
                "oid": fill.oid,
                "trade_id": fill.trade_id,
                "fill_timestamp_ms": fill.timestamp_ms,
                "fill_price": fill.price,
                "fill_size": fill.size,
                "fill_side": fill.side,
                "liquidity_side": "taker" if fill.crossed else "maker",
                "mark_timestamp_ms": book.exchange_timestamp_ms,
                "mark_price": book.mid_price,
                "horizon_ms": horizon_ms,
                "target_horizon_ms": self._markout_horizon_ms,
                "horizon_lateness_ms": horizon_ms - self._markout_horizon_ms,
                "recovered_after_restart": recovered_after_restart,
                "markout_bps": round(markout, 10),
            },
        )

    def _emit_liquidation_distance(self, book: SolBookSnapshot) -> None:
        position = self._latest_position
        if position is None or position.size_signed == 0.0:
            return
        liquidation = position.liquidation_price
        if liquidation is None:
            return
        sign = 1.0 if position.size_signed > 0.0 else -1.0
        distance = sign * (book.mid_price - liquidation) / book.mid_price * 100.0
        self._emit(
            "liquidation_distance",
            {
                "strategy_id": self._strategy_id,
                "side": "long" if sign > 0.0 else "short",
                "mark_price": book.mid_price,
                "liquidation_price": liquidation,
                "distance_pct": round(distance, 10),
                "liquidatable": distance <= 0.0,
            },
        )


def _quality_payload(
    strategy_id: str,
    fill: SolFill,
    expected: float,
    slippage: float,
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "oid": fill.oid,
        "trade_id": fill.trade_id,
        "fill_timestamp_ms": fill.timestamp_ms,
        "expected_price": expected,
        "fill_price": fill.price,
        "fill_size": fill.size,
        "fill_side": fill.side,
        "liquidity_side": "taker" if fill.crossed else "maker",
        "slippage_bps": round(slippage, 10),
    }


def _expected_price(payload: Mapping[str, object]) -> float | None:
    for key in ("expected_price", "mark_price", "limit_price", "trigger_price"):
        value = payload.get(key)
        if _positive_number(value):
            return float(value)
    return None


def _fill_sign(fill: SolFill) -> float:
    side = fill.side.strip().upper()
    if side in {"B", "BUY"}:
        return 1.0
    if side in {"A", "S", "SELL"}:
        return -1.0
    raise ValueError(f"unsupported Hyperliquid fill side: {fill.side!r}")


def _event_keys(
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


def _fill_from_payload(payload: Mapping[str, object]) -> SolFill | None:
    oid = payload.get("oid")
    timestamp = payload.get("venue_timestamp_ms")
    price, size = payload.get("price"), payload.get("size")
    fee, closed = payload.get("fee_usd"), payload.get("closed_pnl_usd")
    side, direction = payload.get("side"), payload.get("direction")
    fee_token, transaction = payload.get("fee_token"), payload.get("transaction_hash")
    trade_id = ledger_trade_id(payload, label="fill trade_id")
    crossed = payload.get("crossed")
    if not _valid_fill_fields(
        oid,
        timestamp,
        price,
        size,
        fee,
        closed,
        side,
        direction,
        fee_token,
        transaction,
        crossed,
    ):
        return None
    return SolFill(
        oid=int(oid),
        price=float(price),
        size=float(size),
        side=str(side),
        timestamp_ms=int(timestamp),
        fee_usd=float(fee),
        fee_token=str(fee_token),
        closed_pnl_usd=float(closed),
        crossed=bool(crossed),
        direction=str(direction),
        transaction_hash=str(transaction),
        trade_id=trade_id,
    )


def _valid_fill_fields(*values: object) -> bool:
    oid, timestamp, price, size, fee, closed = values[:6]
    side, direction, fee_token, transaction, crossed = values[6:]
    return (
        _positive_int(oid)
        and _positive_int(timestamp)
        and _positive_number(price)
        and _positive_number(size)
        and _number(fee)
        and _number(closed)
        and all(
            isinstance(value, str)
            for value in (side, direction, fee_token, transaction)
        )
        and isinstance(crossed, bool)
    )


def _is_ack_payload(payload: Mapping[str, object]) -> bool:
    return isinstance(payload.get("accepted"), bool) and "status" in payload


def _record_timestamp_ms(record: Mapping[str, object]) -> int | None:
    value = record.get("observed_at_utc")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return int(parsed.timestamp() * 1_000)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_number(value: object) -> bool:
    return _number(value) and float(value) > 0.0


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
