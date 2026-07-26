"""Event-runtime order and cost details reconstructed from the shadow ledger."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Literal

_SEQUENCE = re.compile(r"-(\d{8})$")


@dataclass(frozen=True)
class PendingTargetResume:
    """One reduce-only target that remained active at process shutdown."""

    client_order_id: str
    side: Literal["buy", "sell"]
    quantity: float
    limit_price: float
    submitted_at: str
    cumulative_quantity: float
    remaining_quantity: float
    conviction: float | None = None
    conviction_source: str | None = None
    metalabel_p: float | None = None
    metalabel_bundle_id: str | None = None


@dataclass(frozen=True)
class EventResumeDetails:
    """Additional state required only by the event-driven shadow runtime."""

    execution_model: str
    active_targets: tuple[PendingTargetResume, ...]
    next_order_sequence: int
    open_position_fees_usd: float
    open_position_funding_net_usd: float
    liquidation_cooldown_until_ms: int | None


def event_resume_details(rows: list[dict[str, object]]) -> EventResumeDetails:
    """Recover active target, identity, and open-position cost state."""
    fees, funding = _open_costs(rows)
    return EventResumeDetails(
        execution_model=_execution_model(rows),
        active_targets=_active_targets(rows),
        next_order_sequence=_next_sequence(rows),
        open_position_fees_usd=fees,
        open_position_funding_net_usd=funding,
        liquidation_cooldown_until_ms=_liquidation_cooldown(rows),
    )


def _execution_model(rows: list[dict[str, object]]) -> str:
    return next(
        (
            value
            for row in reversed(rows)
            if isinstance((value := row.get("execution_model")), str) and value
        ),
        "legacy_bar_through_v1",
    )


def _active_targets(
    rows: list[dict[str, object]],
) -> tuple[PendingTargetResume, ...]:
    active: dict[str, PendingTargetResume] = {}
    for row in rows:
        order_id = row.get("client_order_id")
        if not isinstance(order_id, str) or not order_id:
            continue
        action = row.get("action")
        if action == "submit_target":
            target = _parse_target(row, order_id)
            active[order_id] = target
        elif action in {
            "cancel_target",
            "rejected_target",
            "expired_target",
            "liquidation",
            "partial_liquidation",
            "backstop_liquidation",
        }:
            if action in {
                "liquidation",
                "partial_liquidation",
                "backstop_liquidation",
            }:
                active.clear()
            else:
                active.pop(order_id, None)
        elif action in {"reduce_target", "close"} and order_id in active:
            remaining = _number(row, "remaining_qty") or 0.0
            if remaining <= 0.0:
                active.pop(order_id, None)
            else:
                current = active[order_id]
                active[order_id] = replace(
                    current,
                    cumulative_quantity=_number(row, "cumulative_filled_qty") or 0.0,
                    remaining_quantity=remaining,
                )
    return tuple(active.values())


def _parse_target(
    row: dict[str, object],
    order_id: str,
) -> PendingTargetResume:
    side = row.get("side")
    submitted_at = row.get("feed_ts")
    quantity = _required_number(row, "requested_qty")
    limit = _required_number(row, "fill_px")
    if side not in {"buy", "sell"} or not isinstance(submitted_at, str):
        raise ValueError("event target ledger state is incomplete")
    return PendingTargetResume(
        client_order_id=order_id,
        side=side,
        quantity=quantity,
        limit_price=limit,
        submitted_at=submitted_at,
        cumulative_quantity=_number(row, "cumulative_filled_qty") or 0.0,
        remaining_quantity=_number(row, "remaining_qty") or quantity,
        conviction=_number(row, "conviction"),
        conviction_source=_optional_text(row, "conviction_source"),
        metalabel_p=_number(row, "metalabel_p"),
        metalabel_bundle_id=_optional_text(row, "metalabel_bundle_id"),
    )


def _next_sequence(rows: list[dict[str, object]]) -> int:
    maximum = 0
    for row in rows:
        value = row.get("client_order_id")
        match = _SEQUENCE.search(value) if isinstance(value, str) else None
        if match is not None:
            maximum = max(maximum, int(match.group(1)))
    return maximum + 1


def _open_costs(rows: list[dict[str, object]]) -> tuple[float, float]:
    fees = 0.0
    funding = 0.0
    for row in rows:
        position = _number(row, "position_qty")
        if position is None:
            continue
        if position == 0.0:
            fees = 0.0
            funding = 0.0
            continue
        fees += _number(row, "fee_usd") or 0.0
        funding -= _number(row, "funding_payment_usd") or 0.0
    return fees, funding


def _liquidation_cooldown(rows: list[dict[str, object]]) -> int | None:
    """Return the last active venue liquidation cooldown boundary."""
    for row in reversed(rows):
        position = _number(row, "position_qty")
        if position == 0.0:
            return None
        value = _number(row, "liquidation_cooldown_until_ms")
        if value is not None and value >= 0.0:
            return int(value)
    return None


def _required_number(row: dict[str, object], key: str) -> float:
    value = _number(row, key)
    if value is None or value <= 0.0:
        raise ValueError(f"event target requires positive {key}")
    return value


def _number(row: dict[str, object], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _optional_text(row: dict[str, object], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) and value else None
