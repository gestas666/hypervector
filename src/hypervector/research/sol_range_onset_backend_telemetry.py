"""Flatten authoritative SOL shadow state for the read-only backend TUI."""

from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Mapping

from hypervector.data.hl_events import AssetContextEvent, BookLevel, L2SnapshotEvent
from hypervector.research.sol_range_onset_shadow_models import (
    SharedCapitalSnapshot,
    SolShadowPosition,
    SolShadowSnapshot,
)

_ACTION_MAP = {
    "entry_filled": "entry",
    "position_closed": "close",
    "funding_settled": "funding",
}


def build_sol_backend_rows(
    *,
    records: tuple[dict[str, object], ...],
    snapshot: SolShadowSnapshot,
    capital: SharedCapitalSnapshot | None,
    latest_book: L2SnapshotEvent | None,
    latest_context: AssetContextEvent | None,
    recorded_at_ms: int,
) -> tuple[dict[str, object], ...]:
    """Project one mutation batch and latest public state without authority."""
    _positive_integer(recorded_at_ms, "recorded_at_ms")
    rows = [
        row
        for record in records
        if (row := _execution_row(record, capital)) is not None
    ]
    if latest_book is not None:
        rows.append(_book_row(latest_book))
    rows.append(_state_row(snapshot, capital, latest_context, recorded_at_ms))
    return tuple(_no_submit(row) for row in rows)


def _execution_row(
    record: Mapping[str, object],
    capital: SharedCapitalSnapshot | None,
) -> dict[str, object] | None:
    _validate_record(record)
    action = record.get("action")
    if not isinstance(action, str) or action not in _ACTION_MAP:
        return None
    event_time_ms = _positive_integer(record.get("event_time_ms"), "event_time_ms")
    row = {
        key: value
        for key, value in record.items()
        if key
        not in {
            "action",
            "event_time_ms",
            "execution_authority",
            "submitted",
            "place_attempted",
        }
    }
    mapped = _ACTION_MAP[action]
    if mapped == "entry":
        direction = record.get("direction")
        if direction not in {"long", "short"}:
            raise ValueError("entry telemetry direction must be long or short")
        mapped = f"enter_{direction}"
    row.update({"feed_ts": _iso_timestamp(event_time_ms), "action": mapped})
    _attach_realized_equity(row, capital)
    return row


def _book_row(event: L2SnapshotEvent) -> dict[str, object]:
    bid = event.bids[0].price
    ask = event.asks[0].price
    mid = (bid + ask) / 2.0
    bid_depth = sum(level.size for level in event.bids[:5])
    ask_depth = sum(level.size for level in event.asks[:5])
    total_depth = bid_depth + ask_depth
    return {
        "feed_ts": _iso_timestamp(event.exchange_ts_ms),
        "action": "book_observation",
        "source": event.source,
        "exchange_ts_ms": event.exchange_ts_ms,
        "recv_ts_ms": event.received_ts_ns / 1_000_000.0,
        "mid_px": mid,
        "spread_bps": (ask - bid) / mid * 10_000.0,
        "bid_depth_ratio": bid_depth / ask_depth,
        "opi": (bid_depth - ask_depth) / total_depth,
        "bids": _levels(event.bids),
        "asks": _levels(event.asks),
    }


def _state_row(
    snapshot: SolShadowSnapshot,
    capital: SharedCapitalSnapshot | None,
    context: AssetContextEvent | None,
    recorded_at_ms: int,
) -> dict[str, object]:
    position = snapshot.position
    unrealized = _unrealized(position, context)
    row: dict[str, object] = {
        "feed_ts": _iso_timestamp(recorded_at_ms),
        "action": "shadow_state",
        "shadow_status": snapshot.status,
        "realized_pnl": snapshot.sol_realized_delta_usd,
        "unrealized_pnl": unrealized or 0.0,
        "position_qty": _position_quantity(position),
        "position_avg_px": 0.0 if position is None else position.entry_price,
        "valuation_status": "observed_mark"
        if context is not None
        else "mark_unavailable",
    }
    if capital is not None:
        row["equity"] = (
            capital.equity_usd + snapshot.sol_realized_delta_usd + (unrealized or 0.0)
        )
        row["shared_reserved_margin_usd"] = capital.reserved_margin_usd
        row["shared_capital_run_id"] = capital.source_run_id
    if position is not None:
        row.update(_position_fields(position))
    if context is not None:
        row.update(_context_fields(context, recorded_at_ms))
    return row


def _position_fields(position: SolShadowPosition) -> dict[str, object]:
    return {
        "liquidation_price": position.liquidation_price,
        "stop_price": position.stop_price,
        "allocated_margin_usd": position.margin_usd,
        "entry_fee_usd": position.entry_fee_usd,
        "funding_payment_usd": position.funding_cashflow_usd,
    }


def _context_fields(
    context: AssetContextEvent,
    recorded_at_ms: int,
) -> dict[str, object]:
    return {
        "mark_px": context.mark_price,
        "oracle_price": context.oracle_price,
        "funding_rate_hourly": context.funding_rate_hourly,
        "mark_observed_ts_ms": context.observed_ts_ms,
        "mark_age_ms": recorded_at_ms - context.observed_ts_ms,
        "mark_timestamp_source": context.timestamp_source,
    }


def _unrealized(
    position: SolShadowPosition | None,
    context: AssetContextEvent | None,
) -> float | None:
    if position is None:
        return 0.0
    if context is None:
        return None
    sign = 1.0 if position.direction == "long" else -1.0
    return sign * position.quantity * (context.mark_price - position.entry_price)


def _position_quantity(position: SolShadowPosition | None) -> float:
    if position is None:
        return 0.0
    sign = 1.0 if position.direction == "long" else -1.0
    return sign * position.quantity


def _attach_realized_equity(
    row: dict[str, object],
    capital: SharedCapitalSnapshot | None,
) -> None:
    delta = row.get("equity_delta_usd")
    if not isinstance(delta, (int, float)) or isinstance(delta, bool):
        return
    value = float(delta)
    if not math.isfinite(value):
        raise ValueError("equity_delta_usd must be finite")
    row["realized_pnl"] = value
    if capital is not None:
        row["equity"] = capital.equity_usd + value


def _levels(levels: tuple[BookLevel, ...]) -> list[dict[str, float]]:
    return [{"price": level.price, "size": level.size} for level in levels[:5]]


def _validate_record(record: Mapping[str, object]) -> None:
    if record.get("execution_authority") != "none":
        raise ValueError("SOL telemetry record execution authority must remain none")
    if (
        record.get("submitted") is not False
        or record.get("place_attempted") is not False
    ):
        raise ValueError("SOL telemetry record must remain no-submit")


def _no_submit(row: dict[str, object]) -> dict[str, object]:
    return {
        **row,
        "execution_authority": "none",
        "model_authority": "none",
        "submitted": False,
        "place_attempted": False,
    }


def _iso_timestamp(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1_000.0, tz=UTC).isoformat()


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
