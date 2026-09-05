"""Strict fill and funding indexes shared by cohort lifecycle research."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_live_audit_values import (
    nonnegative_int,
    number,
    payload,
)

Record = Mapping[str, object]
SIZE_TOLERANCE = 0.000_000_001


@dataclass(frozen=True)
class FillAggregate:
    """Exact aggregate for every venue fill leg sharing one order identity."""

    size: float
    notional_usd: float
    fee_usd: float
    closed_pnl_usd: float


@dataclass(frozen=True)
class _Fill:
    oid: int
    trade_id: int
    price: float
    size: float
    fee_usd: float
    closed_pnl_usd: float


def build_fill_index(
    asset_records: Mapping[str, Sequence[Record]],
) -> dict[tuple[str, int], FillAggregate]:
    """Aggregate deduplicated venue fill legs by symbol and order ID."""
    grouped: dict[tuple[str, int], dict[int, _Fill]] = {}
    for symbol, rows in asset_records.items():
        for row in rows:
            if row.get("event_type") != "fill":
                continue
            fill = _parse_fill(payload(row))
            trades = grouped.setdefault((symbol, fill.oid), {})
            prior = trades.get(fill.trade_id)
            if prior is not None and prior != fill:
                raise ValueError(f"{symbol} fill trade identity is conflicting")
            trades[fill.trade_id] = fill
    return {
        key: _aggregate_fills(tuple(values.values())) for key, values in grouped.items()
    }


def build_funding_index(
    asset_records: Mapping[str, Sequence[Record]],
) -> dict[str, dict[int, float]]:
    """Index exact funding cashflows by symbol and venue timestamp."""
    output: dict[str, dict[int, float]] = {}
    for symbol, rows in asset_records.items():
        timeline = output.setdefault(symbol, {})
        for row in rows:
            if row.get("event_type") != "funding":
                continue
            values = payload(row)
            timestamp_ms = nonnegative_int(
                values.get("venue_timestamp_ms"), "funding timestamp"
            )
            delta = number(values.get("usdc_delta"), "funding delta")
            prior = timeline.get(timestamp_ms)
            if prior is not None and prior != delta:
                raise ValueError(f"{symbol} funding timestamp is conflicting")
            timeline[timestamp_ms] = delta
    return output


def required_fill(
    fills: Mapping[tuple[str, int], FillAggregate],
    identity: tuple[str, int],
    leg: Record,
    label: str,
    context: str,
) -> FillAggregate:
    """Return one exact fill aggregate and require lifecycle-size parity."""
    fill = fills.get(identity)
    if fill is None:
        raise ValueError(f"{identity[0]} {context} lacks exact {label} fill evidence")
    expected_size = positive_number(leg.get("size"), f"{label} size")
    if not math.isclose(fill.size, expected_size, abs_tol=SIZE_TOLERANCE):
        raise ValueError(f"{identity[0]} {context} {label} size is inconsistent")
    return fill


def funding_sum(values: Mapping[int, float], start_ms: int, end_ms: int) -> float:
    """Sum venue funding cashflows over one inclusive lifecycle interval."""
    return sum(
        delta
        for timestamp_ms, delta in values.items()
        if start_ms <= timestamp_ms <= end_ms
    )


def positive_int(value: object, label: str) -> int:
    """Parse one strictly positive integer evidence value."""
    parsed = nonnegative_int(value, label)
    if parsed < 1:
        raise ValueError(f"{label} must be positive")
    return parsed


def positive_number(value: object, label: str) -> float:
    """Parse one strictly positive finite numeric evidence value."""
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _parse_fill(values: Record) -> _Fill:
    price = positive_number(values.get("price"), "fill price")
    size = positive_number(values.get("size"), "fill size")
    fee = number(values.get("fee_usd"), "fill fee")
    if fee < 0.0:
        raise ValueError("fill fee must be nonnegative")
    return _Fill(
        positive_int(values.get("oid"), "fill oid"),
        positive_int(values.get("trade_id"), "fill trade id"),
        price,
        size,
        fee,
        number(values.get("closed_pnl_usd", 0.0), "fill closed PnL"),
    )


def _aggregate_fills(fills: Sequence[_Fill]) -> FillAggregate:
    return FillAggregate(
        sum(fill.size for fill in fills),
        sum(fill.price * fill.size for fill in fills),
        sum(fill.fee_usd for fill in fills),
        sum(fill.closed_pnl_usd for fill in fills),
    )
