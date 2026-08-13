"""Reusable causal L2 context for cohort research diagnostics."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    nonnegative_int,
    number,
    payload,
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class CausalBookSnapshot:
    """One validated book observation available to a causal decision."""

    recv_ts_ms: int
    opi: float
    spread_bps: float
    bid_depth_ratio: float
    mid_px: float
    best_bid: float
    best_ask: float


def build_causal_book_indexes(
    asset_records: Mapping[str, Sequence[Record]],
) -> dict[str, tuple[CausalBookSnapshot, ...]]:
    """Index validated book observations by symbol and receive timestamp."""
    output: dict[str, tuple[CausalBookSnapshot, ...]] = {}
    for symbol, records in asset_records.items():
        snapshots = tuple(
            sorted(
                (
                    _book_snapshot(row)
                    for row in event_rows(records, "book_observation")
                ),
                key=lambda item: item.recv_ts_ms,
            )
        )
        if len({item.recv_ts_ms for item in snapshots}) != len(snapshots):
            raise ValueError(f"{symbol} order-book receive timestamps must be unique")
        output[symbol] = snapshots
    return output


def latest_prior_book(
    snapshots: Sequence[CausalBookSnapshot],
    decision_time_ms: int,
    maximum_age_ms: int,
) -> tuple[str, CausalBookSnapshot | None]:
    """Return the latest nonfuture book and its matched, stale, or missing state."""
    timestamps = [item.recv_ts_ms for item in snapshots]
    index = bisect_right(timestamps, decision_time_ms) - 1
    if index < 0:
        return "missing", None
    snapshot = snapshots[index]
    if decision_time_ms - snapshot.recv_ts_ms > maximum_age_ms:
        return "stale", None
    return "matched", snapshot


def earliest_at_or_after_book(
    snapshots: Sequence[CausalBookSnapshot],
    target_time_ms: int,
    maximum_lateness_ms: int,
) -> tuple[str, CausalBookSnapshot | None]:
    """Return the first future book within a bounded observation delay."""
    if target_time_ms < 0 or maximum_lateness_ms < 1:
        raise ValueError("book target and maximum lateness are invalid")
    timestamps = [item.recv_ts_ms for item in snapshots]
    index = bisect_left(timestamps, target_time_ms)
    if index >= len(snapshots):
        return "censored", None
    snapshot = snapshots[index]
    if snapshot.recv_ts_ms - target_time_ms > maximum_lateness_ms:
        return "gap", None
    return "matched", snapshot


def _book_snapshot(row: Record) -> CausalBookSnapshot:
    values = payload(row)
    recv_ms = nonnegative_int(values.get("recv_ts_ms"), "book receive timestamp")
    opi = number(values.get("opi"), "book OPI")
    spread = number(values.get("spread_bps"), "book spread")
    depth = number(values.get("bid_depth_ratio"), "book depth ratio")
    mid_px = number(values.get("mid_px"), "book midpoint")
    if not -1.0 <= opi <= 1.0:
        raise ValueError("book OPI must be within [-1, 1]")
    if spread < 0.0 or depth <= 0.0 or mid_px <= 0.0:
        raise ValueError("book spread and depth ratio are invalid")
    half_spread = mid_px * spread / 20_000.0
    best_bid = mid_px - half_spread
    best_ask = mid_px + half_spread
    if best_bid <= 0.0 or best_bid > best_ask:
        raise ValueError("book executable BBO is invalid")
    return CausalBookSnapshot(
        recv_ms,
        opi,
        spread,
        depth,
        mid_px,
        best_bid,
        best_ask,
    )
