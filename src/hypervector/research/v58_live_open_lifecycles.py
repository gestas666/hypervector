"""Validated actual-fill context for open V58 live lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isclose, isfinite

from hypervector.research.v58_live_profit_lock_context import (
    extract_v58_live_profit_lock_challenger,
)

Record = Mapping[str, object]


def extract_v58_live_open_lifecycles(
    audit: Record, *, run_id: str, symbols: Sequence[str]
) -> dict[str, object]:
    """Return source-reconciled open fills without creating exit-fill claims."""
    execution = _mapping(audit.get("execution"), "execution")
    reflections = _mapping(audit.get("open_trade_reflections"), "reflections")
    _require_contract(reflections)
    positions = _records(execution.get("open_positions"), "open positions")
    fills = _records(execution.get("fill_details"), "fill details")
    trades = _records(reflections.get("trades"), "open reflections")
    _require_counts(execution, reflections, positions, trades)
    health = _mapping(_mapping(audit.get("health"), "health").get("assets"), "assets")
    symbol_set = set(symbols)
    if len(symbol_set) != len(tuple(symbols)):
        raise ValueError("V58 live open-lifecycle symbols must be unique")
    rows = [
        _trade_payload(trade, positions, fills, health, run_id, symbol_set)
        for trade in trades
    ]
    if len({row["symbol"] for row in rows}) != len(rows):
        raise ValueError("V58 live open lifecycles must use unique symbols")
    return {
        "measurement_scope": "actual_open_live_lifecycles",
        "open_lifecycles": len(rows),
        "trades": rows,
        "portfolio_summary": _portfolio_summary(rows),
        "actual_entry_fills_claimed": bool(rows),
        "actual_exit_fills_claimed": False,
        "marked_pnl_is_provisional": bool(rows),
        "execution_authority": "none",
    }


def _trade_payload(
    trade: Record,
    positions: Sequence[Record],
    fills: Sequence[Record],
    health: Record,
    run_id: str,
    symbols: set[str],
) -> dict[str, object]:
    symbol = _text(trade.get("symbol"), "open symbol")
    side = _side(trade.get("side"))
    source_run_id = _text(trade.get("source_run_id"), "source run id")
    lifecycle = _lifecycle_id(trade.get("lifecycle_id"), symbol, symbols)
    entry = _mapping(trade.get("entry"), "open entry")
    marked = _mapping(trade.get("marked_economics"), "marked economics")
    position = _position(positions, symbol)
    _require_position(position, marked, entry, symbol, side)
    stop = _mapping(trade.get("protective_stop"), "protective stop")
    stop_oid = _positive_integer(stop.get("oid"), "protective stop oid")
    _require_health(health, symbol, side, entry, stop_oid)
    plan = _mapping(trade.get("exit_plan"), "exit plan")
    _require_plan(plan)
    return {
        "lifecycle_id": lifecycle,
        "runtime_run_id": run_id,
        "source_run_id": source_run_id,
        "symbol": symbol,
        "strategy_id": _text(trade.get("strategy_id"), "strategy id"),
        "side": side,
        "actual_entry_fill_claim": True,
        "actual_exit_fill_claim": False,
        "entry_price": _positive_number(entry.get("price"), "entry price"),
        "entry_size": _positive_number(entry.get("size"), "entry size"),
        "entry_time_ms": _positive_integer(
            entry.get("venue_timestamp_ms"), "entry time"
        ),
        "entry_execution_quality": _entry_execution_quality(
            trade, entry, marked, fills, source_run_id
        ),
        "actual_completed_path": _actual_completed_path(trade, entry, marked, side),
        "profit_protection_estimate": _profit_protection_estimate(trade, marked),
        "profit_lock_challenger": extract_v58_live_profit_lock_challenger(trade),
        **_marked_payload(marked),
        "protective_stop_oid": stop_oid,
        "protective_stop_trigger_price": _positive_number(
            stop.get("trigger_price"), "protective stop trigger"
        ),
        **_exit_payload(plan),
        "marked_pnl_is_provisional": True,
    }


def _actual_completed_path(
    trade: Record, entry: Record, marked: Record, side: str
) -> dict[str, object]:
    path = _mapping(trade.get("path_since_entry"), "completed entry path")
    if path.get("status") != "observed":
        raise ValueError("V58 live completed entry path is not observed")
    completed = _positive_integer(path.get("completed_bars"), "completed bars")
    first = _positive_integer(path.get("first_timestamp_ms"), "first path time")
    last = _positive_integer(path.get("last_timestamp_ms"), "last path time")
    entry_time = _positive_integer(entry.get("venue_timestamp_ms"), "entry time")
    if first < entry_time or last < first:
        raise ValueError("V58 live completed entry path time is inconsistent")
    entry_price = _positive_number(entry.get("price"), "entry price")
    high = _positive_number(path.get("highest_price"), "path high")
    low = _positive_number(path.get("lowest_price"), "path low")
    if high < low:
        raise ValueError("V58 live completed entry path prices are inconsistent")
    sign = 1.0 if side == "long" else -1.0
    favorable_price = high if side == "long" else low
    adverse_price = low if side == "long" else high
    mfe = max(0.0, sign * (favorable_price / entry_price - 1.0) * 10_000.0)
    mae = max(0.0, -sign * (adverse_price / entry_price - 1.0) * 10_000.0)
    mark = _positive_number(marked.get("mark_price"), "mark price")
    current = sign * (mark / entry_price - 1.0) * 10_000.0
    giveback = max(0.0, mfe - current)
    expected = (mfe, mae, current, giveback)
    fields = (
        "maximum_favorable_excursion_bps",
        "maximum_adverse_excursion_bps",
        "current_directional_return_bps",
        "peak_giveback_bps",
    )
    values = tuple(_number(path.get(field), field) for field in fields)
    if any(
        not isclose(value, target, abs_tol=1e-8)
        for value, target in zip(values, expected)
    ):
        raise ValueError("V58 live completed entry path metrics do not reconcile")
    return {
        "completed_bars": completed,
        "price_source": _text(path.get("excursion_price_source"), "path source"),
        **dict(zip(fields, values)),
        "continuous_path_claim": False,
        "measurement_scope": "actual_fill_completed_candle_path",
    }


def _profit_protection_estimate(trade: Record, marked: Record) -> dict[str, object]:
    protection = _mapping(trade.get("profit_protection"), "profit protection")
    status = _text(protection.get("status"), "profit protection status")
    reported = _number(protection.get("reported_marked_net_pnl_usd"), "reported net")
    marked_net = _number(
        marked.get("active_lifecycle_marked_net_pnl_usd"), "marked net"
    )
    if not isclose(reported, marked_net, abs_tol=1e-8):
        raise ValueError("V58 live profit-protection marked net is inconsistent")
    current = _number(protection.get("estimated_exit_now_net_usd"), "exit-now net")
    stop = _number(protection.get("estimated_stop_net_usd"), "stop exit")
    giveback = _nonnegative_number(
        protection.get("marked_to_stop_giveback_usd"), "marked-to-stop giveback"
    )
    if not isclose(giveback, current - stop, abs_tol=1e-8):
        raise ValueError("V58 live profit-protection giveback is inconsistent")
    fraction_value = protection.get("protected_profit_fraction")
    fraction = (
        None
        if fraction_value is None
        else _number(fraction_value, "protected fraction")
    )
    if fraction is None and status != "no_open_profit":
        raise ValueError("V58 protected-profit fraction is unexpectedly unavailable")
    if fraction is not None and not 0.0 <= fraction <= 1.0:
        raise ValueError("V58 live protected-profit fraction is outside [0, 1]")
    return {
        "status": status,
        "estimated_exit_now_net_usd": current,
        "estimated_stop_net_usd": stop,
        "marked_to_stop_giveback_usd": giveback,
        "protected_profit_fraction": fraction,
        "method": _text(protection.get("method"), "profit protection method"),
        "actual_exit_fill_claim": False,
    }


def _entry_execution_quality(
    trade: Record,
    entry: Record,
    marked: Record,
    fills: Sequence[Record],
    source_run_id: str,
) -> dict[str, object]:
    lifecycle = _text(trade.get("lifecycle_id"), "lifecycle id")
    entry_oid = _positive_integer(int(lifecycle.rsplit(":", 1)[1]), "entry oid")
    matches = [
        fill
        for fill in fills
        if fill.get("oid") == entry_oid and fill.get("origin_run_id") == source_run_id
    ]
    if len(matches) != 1:
        raise ValueError("V58 live entry-fill coverage is inconsistent")
    fill = matches[0]
    side = _side(trade.get("side"))
    expected = {
        "operation": "entry",
        "strategy_id": trade.get("strategy_id"),
        "symbol": trade.get("symbol"),
        "side": "B" if side == "long" else "A",
        "direction": "Open Long" if side == "long" else "Open Short",
        "price": entry.get("price"),
        "size": entry.get("size"),
        "venue_timestamp_ms": entry.get("venue_timestamp_ms"),
        "fee_usd": marked.get("fees_usd"),
    }
    if any(fill.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 live entry-fill identity is inconsistent")
    return {
        "trade_id": _positive_integer(fill.get("trade_id"), "entry trade id"),
        "expected_price": _positive_number(
            fill.get("expected_price"), "expected price"
        ),
        "slippage_bps": _number(fill.get("slippage_bps"), "entry slippage"),
        "acknowledgement_latency_ms": _nonnegative_integer(
            fill.get("acknowledgement_latency_ms"), "entry acknowledgement latency"
        ),
        "markout_bps": _number(fill.get("markout_bps"), "entry markout"),
        "markout_horizon_ms": _positive_integer(
            fill.get("markout_horizon_ms"), "entry markout horizon"
        ),
        "measurement_scope": "actual_venue_entry_fill",
    }


def _marked_payload(marked: Record) -> dict[str, object]:
    unrealized = _number(marked.get("unrealized_pnl_usd"), "unrealized pnl")
    fees = _nonnegative_number(marked.get("fees_usd"), "fees")
    funding = _number(marked.get("funding_usd"), "funding")
    net = _number(marked.get("active_lifecycle_marked_net_pnl_usd"), "marked net")
    if not isclose(net, unrealized - fees + funding, abs_tol=1e-8):
        raise ValueError("V58 live marked PnL components do not reconcile")
    return {
        "mark_price": _positive_number(marked.get("mark_price"), "mark price"),
        "mark_price_source": _text(marked.get("mark_price_source"), "mark source"),
        "position_value_usd": _positive_number(
            marked.get("position_value_usd"), "position value"
        ),
        "margin_used_usd": _positive_number(
            marked.get("margin_used_usd"), "margin used"
        ),
        "leverage": _positive_integer(marked.get("leverage"), "leverage"),
        "unrealized_pnl_usd": unrealized,
        "fees_usd": fees,
        "funding_usd": funding,
        "marked_net_pnl_usd": net,
    }


def _portfolio_summary(rows: Sequence[Record]) -> dict[str, object]:
    symbols = sorted(_text(row.get("symbol"), "portfolio symbol") for row in rows)
    entry_notional = sum(
        _positive_number(row.get("entry_price"), "entry price")
        * _positive_number(row.get("entry_size"), "entry size")
        for row in rows
    )
    position_value = sum(
        _positive_number(row.get("position_value_usd"), "position value")
        for row in rows
    )
    margin = sum(
        _positive_number(row.get("margin_used_usd"), "margin used") for row in rows
    )
    marked = sum(_number(row.get("marked_net_pnl_usd"), "marked net") for row in rows)
    protections = tuple(
        _mapping(row.get("profit_protection_estimate"), "profit protection")
        for row in rows
    )
    exit_now = sum(
        _number(row.get("estimated_exit_now_net_usd"), "exit now")
        for row in protections
    )
    stop = sum(
        _number(row.get("estimated_stop_net_usd"), "stop net") for row in protections
    )
    giveback = sum(
        _nonnegative_number(row.get("marked_to_stop_giveback_usd"), "giveback")
        for row in protections
    )
    if not isclose(giveback, exit_now - stop, abs_tol=1e-8):
        raise ValueError("V58 open-portfolio protection totals do not reconcile")
    return {
        "measurement_scope": "summed_actual_open_live_lifecycles",
        "symbols": symbols,
        "open_lifecycles": len(rows),
        "owned_protective_stops": len(rows),
        "entry_notional_usd": entry_notional,
        "current_position_value_usd": position_value,
        "margin_used_usd": margin,
        "marked_net_pnl_usd": marked,
        "estimated_exit_now_net_usd": exit_now,
        "estimated_stop_net_usd": stop,
        "marked_to_stop_giveback_usd": giveback,
        "estimated_values_include_future_funding_or_slippage": False,
        "actual_exit_fill_claim": False,
        "loss_ceiling_claim": False,
        "joint_probability_claim": False,
        "execution_authority": "none",
    }


def _exit_payload(plan: Record) -> dict[str, object]:
    return {
        "maximum_hold_seconds": _positive_integer(
            plan.get("maximum_hold_seconds"), "maximum hold"
        ),
        "deadline_timestamp_ms": _positive_integer(
            plan.get("deadline_timestamp_ms"), "maximum-hold deadline"
        ),
        "profit_lock_policy": _text(plan.get("profit_lock_policy"), "profit lock"),
        "opposite_intent_exit_scope": _text(
            plan.get("opposite_intent_exit_scope"), "opposite exit scope"
        ),
    }


def _require_contract(reflections: Record) -> None:
    expected = {
        "schema_version": 1,
        "mode": "cohort_open_trade_reflections",
        "scope": "compatible_profile_history",
    }
    if any(reflections.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 live open-reflection contract is invalid")
    contract = _mapping(reflections.get("contract"), "reflection contract")
    required = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError("V58 live open-reflection authority is invalid")


def _require_counts(
    execution: Record,
    reflections: Record,
    positions: Sequence[Record],
    trades: Sequence[Record],
) -> None:
    execution_count = _nonnegative_integer(
        execution.get("open_lifecycles"), "execution open count"
    )
    reflection_count = _nonnegative_integer(
        reflections.get("open_lifecycles"), "reflection open count"
    )
    if execution_count != len(positions) or reflection_count != len(trades):
        raise ValueError("V58 live open-lifecycle counts are inconsistent")
    if execution_count != reflection_count:
        raise ValueError("V58 live execution and reflection counts disagree")


def _require_position(
    position: Record, marked: Record, entry: Record, symbol: str, side: str
) -> None:
    expected = {
        "status": "provisional_open",
        "symbol": symbol,
        "side": side,
        "entry_price": entry.get("price"),
        "size_signed": _signed_size(entry.get("size"), side),
    }
    if any(position.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 live open position identity is inconsistent")
    fields = (
        "mark_price",
        "mark_price_source",
        "position_value_usd",
        "margin_used_usd",
        "leverage",
        "unrealized_pnl_usd",
        "fees_usd",
        "funding_usd",
        "active_lifecycle_marked_net_pnl_usd",
    )
    if any(position.get(field) != marked.get(field) for field in fields):
        raise ValueError("V58 live position and marked economics disagree")


def _require_health(
    health: Record, symbol: str, side: str, entry: Record, stop_oid: int
) -> None:
    row = _mapping(health.get(symbol), f"{symbol} health")
    reported_orders = row.get("open_order_ids")
    orders = (
        [row.get("stop_oid")]
        if reported_orders is None
        else reported_orders
        if isinstance(reported_orders, list)
        else []
    )
    if stop_oid not in orders:
        raise ValueError("V58 live protective stop is absent from health evidence")
    reported_size = row.get("position_size_signed")
    size_matches = reported_size is None or isclose(
        _number(reported_size, "health position size"),
        _signed_size(entry.get("size"), side),
        abs_tol=1e-12,
    )
    if row.get("final_state") != "OPEN" or not size_matches:
        raise ValueError("V58 live open health position is inconsistent")


def _require_plan(plan: Record) -> None:
    if plan.get("source") != "bound_execution_plan":
        raise ValueError("V58 live open exit plan is not bound")
    _positive_integer(plan.get("maximum_hold_seconds"), "maximum hold")
    _positive_integer(plan.get("deadline_timestamp_ms"), "maximum-hold deadline")
    _text(plan.get("profit_lock_policy"), "profit lock")
    _text(plan.get("opposite_intent_exit_scope"), "opposite exit scope")


def _position(positions: Sequence[Record], symbol: str) -> Record:
    matches = [row for row in positions if row.get("symbol") == symbol]
    if len(matches) != 1:
        raise ValueError("V58 live open position coverage is inconsistent")
    return matches[0]


def _lifecycle_id(value: object, symbol: str, symbols: set[str]) -> str:
    if symbol not in symbols:
        raise ValueError("V58 live open-lifecycle identity is invalid")
    text = _text(value, "lifecycle id")
    prefix = f"{symbol}:"
    if not text.startswith(prefix):
        raise ValueError("V58 live lifecycle symbol is inconsistent")
    _positive_integer(int(text.removeprefix(prefix)), "entry oid")
    return text


def _signed_size(value: object, side: str) -> float:
    size = _positive_number(value, "entry size")
    return size if side == "long" else -size


def _side(value: object) -> str:
    side = _text(value, "side")
    if side not in {"long", "short"}:
        raise ValueError("V58 live open side is invalid")
    return side


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ValueError(f"V58 {label} must be an array")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 {label} must be non-empty text")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"V58 {label} must be finite")
    return number


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"V58 {label} must be positive")
    return number


def _nonnegative_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0.0:
        raise ValueError(f"V58 {label} must be nonnegative")
    return number


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"V58 {label} must be a nonnegative integer")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 {label} must be a positive integer")
    return value
