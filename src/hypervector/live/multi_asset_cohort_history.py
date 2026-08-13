"""Compatible cross-run execution history for cohort telemetry."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from hypervector.live.sol_range_onset_live_journal import build_live_journal
from hypervector.live.sol_range_onset_ledger import SolLiveLedger


@dataclass(frozen=True)
class _ExecutionContext:
    strategy_id: str
    operation: str
    expected_price: float | None
    intent_time_ms: int
    acknowledgement_time_ms: int
    exit_reason: str | None


def compatible_execution_rows(ledger: SolLiveLedger) -> list[dict[str, object]]:
    """Return armed rows matching the current profile and execution contract."""
    return [
        row
        for row in ledger.read_all()
        if row.get("profile_id") == ledger.profile_id
        and row.get("profile_fingerprint") == ledger.profile_fingerprint
        and row.get("run_fingerprint") == ledger.run_fingerprint
        and row.get("execution_mode") == "live"
        and row.get("live_armed") is True
        and row.get("execution_authority") == "hyperliquid_mainnet"
    ]


def current_run_rows(
    rows: list[dict[str, object]],
    run_id: str,
) -> list[dict[str, object]]:
    """Restrict compatible history to one current process run."""
    return [row for row in rows if row.get("run_id") == run_id]


def asset_costs(rows: list[dict[str, object]]) -> dict[str, object]:
    """Aggregate unique venue fills and funding over compatible history."""
    fills = _unique_rows(rows, "fill", "trade_id")
    funding = _unique_rows(rows, "funding", "venue_timestamp_ms")
    return {
        "fees_net_usd": _sum_rows(fills, "fee_usd"),
        "funding_net_usd": _sum_rows(funding, "usdc_delta"),
        "realized_pnl_usd": _sum_rows(fills, "closed_pnl_usd"),
        "fill_count": len(fills),
        "cost_scope": "compatible_profile_history",
    }


def fill_payloads(
    symbol: str,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Project unique exact venue fills with lifecycle attribution."""
    contexts = _execution_contexts(rows)
    books = _book_marks(rows)
    trade_details = _trade_details_by_exit_oid(rows)
    active_strategy: str | None = None
    output: list[dict[str, object]] = []
    fill_rows = _unique_rows(rows, "fill", "trade_id")
    remaining_closes = Counter(
        _integer_value(_payload(row), "oid")
        for row in fill_rows
        if _text_value(_payload(row), "direction").lower().startswith("close ")
    )
    for row in fill_rows:
        fill = _payload(row)
        context = contexts.get(_integer_value(fill, "oid"))
        direction = _text_value(fill, "direction")
        strategy, controller = _fill_attribution(
            direction,
            context,
            active_strategy,
        )
        if direction.lower().startswith("open "):
            active_strategy = strategy
        elif direction.lower().startswith("close "):
            remaining_closes[_integer_value(fill, "oid")] -= 1
            if remaining_closes[_integer_value(fill, "oid")] == 0:
                active_strategy = None
        output.append(
            _fill_payload(
                symbol,
                row,
                context,
                books,
                strategy,
                controller,
                trade_details.get(_integer_value(fill, "oid")),
            )
        )
    return output


def latest_book(
    symbol: str,
    rows: list[dict[str, object]],
) -> dict[str, object] | None:
    """Return the latest current-run L2 observation for one symbol."""
    latest = next(
        (
            _payload(row)
            for row in reversed(rows)
            if row.get("event_type") == "book_observation"
        ),
        None,
    )
    return None if latest is None else {"symbol": symbol, **latest}


def _fill_payload(
    symbol: str,
    row: dict[str, object],
    context: _ExecutionContext | None,
    books: tuple[tuple[int, float], ...],
    strategy_id: str,
    exit_controller_id: str | None,
    trade_details: Mapping[str, object] | None,
) -> dict[str, object]:
    fill = _payload(row)
    oid = _integer_value(fill, "oid")
    fill_time = _integer_value(fill, "venue_timestamp_ms")
    price = _number_value(fill, "price")
    side = _text_value(fill, "side")
    markout = _markout(books, fill_time, price, side)
    expected = context.expected_price if context is not None else None
    details = trade_details or _empty_trade_details()
    return {
        "symbol": symbol,
        "strategy_id": strategy_id,
        "exit_controller_id": exit_controller_id,
        "origin_run_id": _text_value(row, "run_id"),
        "operation": context.operation if context else "unknown",
        "trade_id": _integer_value(fill, "trade_id"),
        "oid": oid,
        "venue_timestamp_ms": fill_time,
        "price": price,
        "size": _number_value(fill, "size"),
        "side": side,
        "direction": _text_value(fill, "direction"),
        "fee_usd": _number_value(fill, "fee_usd"),
        "closed_pnl_usd": _number_value(fill, "closed_pnl_usd"),
        "expected_price": expected,
        "slippage_bps": _slippage_bps(expected, price, side),
        "acknowledgement_latency_ms": _latency(context),
        "markout_bps": markout[0],
        "markout_horizon_ms": markout[1],
        "exit_reason": context.exit_reason if context else None,
        **details,
    }


def _trade_details_by_exit_oid(
    rows: list[dict[str, object]],
) -> dict[int, dict[str, object]]:
    if not any(
        row.get("event_type") == "order_acknowledgement"
        and _payload(row).get("operation") == "entry"
        and _payload(row).get("accepted") is True
        for row in rows
    ):
        return {}
    rebased = tuple(
        {**row, "sequence": index} for index, row in enumerate(rows, start=1)
    )
    journal = build_live_journal(rebased)
    trades = journal.get("trades")
    if not isinstance(trades, list):
        raise ValueError("live journal trades must be a list")
    return {_trade_exit_oid(trade): _trade_details(trade) for trade in trades}


def _trade_exit_oid(value: object) -> int:
    if not isinstance(value, Mapping):
        raise ValueError("live journal trade must be an object")
    return _integer_value(value, "exit_oid")


def _trade_details(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("live journal trade must be an object")
    entry = value.get("entry")
    if not isinstance(entry, Mapping):
        raise ValueError("live journal trade entry must be an object")
    return {
        "lifecycle_fees_usd": _number_value(value, "fees_usd"),
        "lifecycle_funding_usd": _number_value(value, "funding_usd"),
        "net_pnl_usd": _number_value(value, "net_pnl_usd"),
        "holding_time_ms": _integer_value(value, "holding_time_ms"),
        "exit_reason": value.get("exit_reason"),
        "entry_price": _number_value(entry, "price"),
        "entry_venue_timestamp_ms": _integer_value(entry, "venue_timestamp_ms"),
    }


def _empty_trade_details() -> dict[str, object]:
    return {
        "lifecycle_fees_usd": None,
        "lifecycle_funding_usd": None,
        "net_pnl_usd": None,
        "holding_time_ms": None,
        "entry_price": None,
        "entry_venue_timestamp_ms": None,
    }


def _fill_attribution(
    direction: str,
    context: _ExecutionContext | None,
    active_strategy: str | None,
) -> tuple[str, str | None]:
    context_strategy = context.strategy_id if context else "unattributed"
    if direction.lower().startswith("close "):
        return active_strategy or context_strategy, context_strategy
    return context_strategy, None


def _execution_contexts(
    rows: list[dict[str, object]],
) -> dict[int, _ExecutionContext]:
    pending: dict[str, tuple[str, str, float | None, int, str | None]] = {}
    contexts: dict[int, _ExecutionContext] = {}
    strategy_id = "unattributed"
    exit_reason: str | None = None
    for row in rows:
        event_type = row.get("event_type")
        payload = _payload(row)
        if event_type == "regime_decision":
            strategy_id = str(payload.get("strategy_id") or strategy_id)
        elif event_type == "close" and payload.get("intent") is True:
            exit_reason = _text_value(payload, "reason")
        elif event_type == "order_intent":
            client_id = _text_value(payload, "client_order_id")
            operation = _text_value(payload, "operation")
            if operation == "entry":
                exit_reason = None
            expected = _optional_number(payload, "mark_price")
            expected = expected or _optional_number(payload, "trigger_price")
            expected = expected or _optional_number(payload, "limit_price")
            pending[client_id] = (
                strategy_id,
                operation,
                expected,
                _observed_time_ms(row),
                exit_reason,
            )
        elif event_type in {
            "order_acknowledgement",
            "stop_order",
            "target_order",
            "close",
        }:
            _bind_acknowledgement(row, payload, pending, contexts)
    return contexts


def _bind_acknowledgement(
    row: dict[str, object],
    payload: dict[str, object],
    pending: dict[str, tuple[str, str, float | None, int, str | None]],
    contexts: dict[int, _ExecutionContext],
) -> None:
    client_id = payload.get("client_order_id")
    if payload.get("accepted") is not True or not isinstance(client_id, str):
        return
    if client_id not in pending:
        return
    oid = _integer_value(payload, "oid")
    strategy_id, operation, expected, started, reason = pending[client_id]
    context = _ExecutionContext(
        strategy_id,
        operation,
        expected,
        started,
        _observed_time_ms(row),
        reason,
    )
    prior = contexts.get(oid)
    if prior is None:
        contexts[oid] = context
        return
    if (
        prior.strategy_id,
        prior.operation,
        prior.expected_price,
        prior.intent_time_ms,
        prior.exit_reason,
    ) != (
        context.strategy_id,
        context.operation,
        context.expected_price,
        context.intent_time_ms,
        context.exit_reason,
    ):
        raise ValueError(f"conflicting execution context for order {oid}")


def _unique_rows(
    rows: list[dict[str, object]],
    event_type: str,
    identity_key: str,
) -> list[dict[str, object]]:
    unique: dict[int, dict[str, object]] = {}
    for row in rows:
        if row.get("event_type") != event_type:
            continue
        identity = _integer_value(_payload(row), identity_key)
        prior = unique.get(identity)
        if prior is not None and _payload(prior) != _payload(row):
            raise ValueError(f"conflicting duplicate {event_type} identity {identity}")
        unique[identity] = row
    return list(unique.values())


def _sum_rows(rows: list[dict[str, object]], key: str) -> float:
    return sum(_number_value(_payload(row), key) for row in rows)


def _book_marks(rows: list[dict[str, object]]) -> tuple[tuple[int, float], ...]:
    return tuple(
        (
            _integer_value(_payload(row), "exchange_ts_ms"),
            _number_value(_payload(row), "mid_px"),
        )
        for row in rows
        if row.get("event_type") == "book_observation"
    )


def _markout(
    books: tuple[tuple[int, float], ...],
    fill_time_ms: int,
    fill_price: float,
    side: str,
) -> tuple[float | None, int | None]:
    eligible = next((item for item in books if item[0] >= fill_time_ms + 5_000), None)
    if eligible is None:
        return None, None
    timestamp, mark = eligible
    direction = 1.0 if side.upper() == "B" else -1.0
    return direction * (mark / fill_price - 1.0) * 10_000.0, timestamp - fill_time_ms


def _slippage_bps(expected: float | None, fill: float, side: str) -> float | None:
    if expected is None:
        return None
    direction = 1.0 if side.upper() == "B" else -1.0
    return direction * (fill / expected - 1.0) * 10_000.0


def _latency(context: _ExecutionContext | None) -> int | None:
    if context is None:
        return None
    return context.acknowledgement_time_ms - context.intent_time_ms


def _payload(row: Mapping[str, object]) -> dict[str, object]:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("asset ledger payload must be an object")
    return payload


def _observed_time_ms(row: Mapping[str, object]) -> int:
    value = row.get("observed_at_utc")
    if not isinstance(value, str):
        raise ValueError("asset ledger row lacks observed_at_utc")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("asset ledger observed_at_utc must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def _integer_value(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"asset ledger {key} must be an integer")
    return value


def _number_value(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"asset ledger {key} must be numeric")
    return float(value)


def _optional_number(values: Mapping[str, object], key: str) -> float | None:
    return None if values.get(key) is None else _number_value(values, key)


def _text_value(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"asset ledger {key} must be non-empty text")
    return value.strip()
