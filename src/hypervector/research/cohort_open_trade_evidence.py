"""Causal completed-candle path evidence for one open cohort trade."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_ignored_provider_exit import (
    build_ignored_provider_exit_observer,
)
from hypervector.research.cohort_live_audit_values import nonnegative_int
from hypervector.research.cohort_mature_profit_floor import (
    build_open_mature_profit_floor_challenger,
)
from hypervector.research.cohort_open_trade_path import (
    build_open_trade_extension_path,
    build_open_trade_path,
)
from hypervector.research.cohort_open_profit_lock_challenger import (
    build_open_profit_lock_challenger,
)
from hypervector.research.cohort_post_soft_trail_challenger import (
    CandleLike,
    build_open_post_soft_trail_status,
)
from hypervector.research.cohort_risk_normalized_profit_lock import (
    build_open_risk_normalized_profit_lock_challenger,
)

Record = Mapping[str, object]


def build_open_trade_evidence(
    candles: Mapping[int, CandleLike],
    side: str,
    entry: Record,
    marked_economics: Record,
    exit_plan: Record,
    as_of_ms: int,
    *,
    provider_evaluations: Sequence[Record] = (),
    protective_stop: Record | None,
) -> dict[str, object]:
    """Build aligned entry, extension, and frozen-trail observations."""
    soft_deadline = nonnegative_int(
        exit_plan.get("soft_deadline_timestamp_ms"),
        "soft deadline timestamp",
    )
    return {
        "path_since_entry": build_open_trade_path(
            candles, side, entry, marked_economics, as_of_ms
        ),
        "path_since_soft_deadline": build_open_trade_extension_path(
            candles,
            side,
            soft_deadline_ms=soft_deadline,
            marked_economics=marked_economics,
            as_of_ms=as_of_ms,
        ),
        "post_soft_trail_challenger": build_open_post_soft_trail_status(
            candles,
            side,
            soft_deadline_ms=soft_deadline,
            as_of_ms=as_of_ms,
        ),
        **_profit_lock_evidence(
            candles,
            side,
            entry,
            protective_stop,
            marked_economics,
            as_of_ms,
        ),
        "ignored_provider_exit_observer": build_ignored_provider_exit_observer(
            provider_evaluations,
            candles,
            side=side,
            entry=entry,
            marked_economics=marked_economics,
            exit_plan=exit_plan,
            as_of_ms=as_of_ms,
        ),
    }


def _profit_lock_evidence(
    candles: Mapping[int, CandleLike],
    side: str,
    entry: Record,
    protective_stop: Record,
    marked_economics: Record,
    as_of_ms: int,
) -> dict[str, object]:
    return {
        "open_profit_lock_challenger": build_open_profit_lock_challenger(
            candles, side, entry, marked_economics, as_of_ms
        ),
        "open_mature_profit_floor_challenger": (
            build_open_mature_profit_floor_challenger(
                candles, side, entry, marked_economics, as_of_ms
            )
        ),
        "open_risk_normalized_profit_lock_challenger": (
            build_open_risk_normalized_profit_lock_challenger(
                candles,
                side,
                entry,
                protective_stop,
                marked_economics,
                as_of_ms,
            )
        ),
    }
