"""Causal SOL aligned-range exact-one-blocker intent provider."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.cohort_candidate_entry_clock import AcceptedEntryClock
from hypervector.live.multi_asset_signal_source import (
    IntentBatch,
    ProviderEvaluation,
    collect_range_onset_bidirectional_intents,
)
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness
from hypervector.live.sol_aligned_range_contract import (
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
    require_sol_aligned_range_strategy,
)

_SOURCE_STRATEGY = "range_onset_bidirectional_v1"
_EXACT_BLOCKERS = ("awaiting_hourly_sma_cross",)
_FIXED_HOLD_MS = 60 * 60 * 1_000
_REARM_MS = 75 * 60 * 1_000
_MAXIMUM_ENTRY_AGE_MS = 60 * 1_000
_MAXIMUM_BOOK_AGE_MS = 30 * 1_000
_TAIL_BYTES = 256 * 1_024
_BOOK_SOURCE = "hyperliquid_mainnet_l2_rest"


@dataclass(frozen=True)
class OrderPressureObservation:
    """One causally received Hyperliquid order-pressure measurement."""

    recv_ts_ms: int
    opi: float

    def __post_init__(self) -> None:
        """Reject malformed timestamps and impossible normalized pressure."""
        if (
            isinstance(self.recv_ts_ms, bool)
            or not isinstance(self.recv_ts_ms, int)
            or self.recv_ts_ms < 0
        ):
            raise ValueError("order-pressure recv_ts_ms must be nonnegative")
        if not math.isfinite(self.opi) or not -1.0 <= self.opi <= 1.0:
            raise ValueError("order pressure must be finite within [-1, 1]")


class OrderPressureSourceProtocol(Protocol):
    """Read the newest causally recorded order-pressure observation."""

    def latest(self) -> OrderPressureObservation | None: ...


class RangeSourceCollectorProtocol(Protocol):
    """Callable contract for the canonical range-onset source."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch: ...


class LedgerOrderPressureSource:
    """Read the latest complete SOL book from a bounded JSONL tail."""

    def __init__(self, path: Path | None) -> None:
        """Bind the asset ledger path without opening it eagerly."""
        self._path = path

    def latest(self) -> OrderPressureObservation | None:
        """Return the newest valid book, or unavailable when none is recorded."""
        path = self._path
        if path is None or not path.is_file():
            return None
        for line in reversed(_complete_tail_lines(path)):
            row = _json_object(line)
            if row.get("event_type") != "book_observation":
                continue
            return _order_pressure(row)
        return None


class SolAlignedRangeOneBlockerCollector:
    """Emit fresh SOL near-misses only when live L2 pressure agrees with side."""

    def __init__(
        self,
        *,
        source_collector: RangeSourceCollectorProtocol = (
            collect_range_onset_bidirectional_intents
        ),
        cohort_ledger: Path | None = None,
        order_pressure_source: OrderPressureSourceProtocol | None = None,
        strategy_id: str = SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
    ) -> None:
        """Bind canonical source, live-book reader, and accepted-entry cadence."""
        self._strategy_id = require_sol_aligned_range_strategy(strategy_id)
        self._source = source_collector
        asset_ledger = (
            None if cohort_ledger is None else cohort_ledger.parent / "sol.jsonl"
        )
        self._pressure = order_pressure_source or LedgerOrderPressureSource(
            asset_ledger
        )
        self._entry_clock = AcceptedEntryClock(
            cohort_ledger,
            strategy_id=self._strategy_id,
            symbol="SOL",
        )
        self._highest_requested_boundary: int | None = None

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return causal readiness and at most one accepted entry per cadence."""
        if symbol != "SOL":
            raise ValueError("SOL aligned-range provider supports SOL only")
        observed_ms = _aware_timestamp_ms(observed_at)
        boundary = _boundary(after_decision_time_ms)
        seed_query = self._is_seed_query(boundary)
        self._entry_clock.refresh()
        source = self._source(
            bars,
            symbol=symbol,
            observed_at=observed_at,
            after_decision_time_ms=after_decision_time_ms,
        )
        evaluations = self._candidate_evaluations(
            source.evaluations,
            observed_ms,
            self._pressure.latest(),
            seed_query,
        )
        intents = (
            ()
            if seed_query
            else tuple(_intent(row) for row in evaluations if row.eligible)
        )
        return IntentBatch(intents, source.latest_decision_time_ms, evaluations)

    def _candidate_evaluations(
        self,
        sources: tuple[ProviderEvaluation, ...],
        observed_ms: int,
        pressure: OrderPressureObservation | None,
        seed_query: bool,
    ) -> tuple[ProviderEvaluation, ...]:
        last_available_ms = self._entry_clock.latest_ms
        output: list[ProviderEvaluation] = []
        for source in sources:
            evaluation = _candidate_evaluation(
                source,
                observed_ms=observed_ms,
                pressure=pressure,
                last_available_ms=last_available_ms,
            )
            output.append(evaluation)
            if evaluation.eligible and not seed_query:
                last_available_ms = observed_ms
        return tuple(output)

    def _is_seed_query(self, boundary: int) -> bool:
        prior = self._highest_requested_boundary
        seed_query = prior is not None and boundary < prior
        self._highest_requested_boundary = max(boundary, prior or 0)
        return seed_query


def _candidate_evaluation(
    source: ProviderEvaluation,
    *,
    observed_ms: int,
    pressure: OrderPressureObservation | None,
    last_available_ms: int | None,
) -> ProviderEvaluation:
    side = source.readiness.side
    exact = _exact_candidate(source, side)
    age_ms = observed_ms - source.decision_time_ms
    fresh = 0 <= age_ms <= _MAXIMUM_ENTRY_AGE_MS
    book_age_ms = None if pressure is None else observed_ms - pressure.recv_ts_ms
    book_fresh = book_age_ms is not None and 0 <= book_age_ms <= _MAXIMUM_BOOK_AGE_MS
    directional_opi = _directional_opi(side, pressure)
    aligned = book_fresh and directional_opi is not None and directional_opi > 0.0
    rearmed = last_available_ms is None or observed_ms >= last_available_ms + _REARM_MS
    eligible = exact and fresh and aligned and rearmed
    reason = _reason(exact, fresh, pressure, book_fresh, aligned, rearmed)
    return ProviderEvaluation(
        strategy_id=SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
        symbol="SOL",
        decision_time_ms=source.decision_time_ms,
        reference_price=source.reference_price,
        decision_action=f"enter_{side}" if eligible else "hold",
        eligible=eligible,
        reason=reason,
        side=side if side in {"long", "short"} else None,
        readiness=_readiness(
            source,
            observed_ms=observed_ms,
            age_ms=age_ms,
            pressure=pressure,
            book_age_ms=book_age_ms,
            directional_opi=directional_opi,
            exact=exact,
            fresh=fresh,
            book_fresh=book_fresh,
            aligned=aligned,
            rearmed=rearmed,
            reason=reason,
            last_available_ms=last_available_ms,
        ),
        trigger="exact_hourly_cross_blocker_opi_aligned_fixed60"
        if eligible
        else "none",
        primary_regime=source.primary_regime,
        state_1m=source.state_1m,
        state_5m=source.state_5m,
        context_15m=source.context_15m,
        confidence=source.confidence,
    )


def _exact_candidate(source: ProviderEvaluation, side: str | None) -> bool:
    return (
        source.strategy_id == _SOURCE_STRATEGY
        and source.symbol == "SOL"
        and side in {"long", "short"}
        and source.readiness.blockers == _EXACT_BLOCKERS
    )


def _directional_opi(
    side: str | None,
    pressure: OrderPressureObservation | None,
) -> float | None:
    if side not in {"long", "short"} or pressure is None:
        return None
    return pressure.opi if side == "long" else -pressure.opi


def _reason(
    exact: bool,
    fresh: bool,
    pressure: OrderPressureObservation | None,
    book_fresh: bool,
    aligned: bool,
    rearmed: bool,
) -> str:
    if not exact:
        return "canonical_exact_one_blocker_absent"
    if not fresh:
        return "candidate_decision_stale"
    if pressure is None:
        return "order_pressure_unavailable"
    if not book_fresh:
        return "order_pressure_stale"
    if not aligned:
        return "order_pressure_opposed"
    if not rearmed:
        return "fixed_horizon_rearm_active"
    return "exact_hourly_cross_blocker_opi_aligned_rearmed"


def _readiness(
    source: ProviderEvaluation,
    *,
    observed_ms: int,
    age_ms: int,
    pressure: OrderPressureObservation | None,
    book_age_ms: int | None,
    directional_opi: float | None,
    exact: bool,
    fresh: bool,
    book_fresh: bool,
    aligned: bool,
    rearmed: bool,
    reason: str,
    last_available_ms: int | None,
) -> SignalReadiness:
    metrics: dict[str, ReadinessMetric] = {
        **source.readiness.metrics,
        "candidate_authority": "staged_profile_only",
        "canonical_source_strategy_id": _SOURCE_STRATEGY,
        "canonical_blockers": ",".join(source.readiness.blockers),
        "exact_hourly_cross_blocker_only": exact,
        "entry_age_seconds": max(0.0, age_ms / 1_000.0),
        "maximum_entry_age_seconds": _MAXIMUM_ENTRY_AGE_MS / 1_000,
        "order_pressure": None if pressure is None else pressure.opi,
        "directional_opi": directional_opi,
        "order_pressure_recv_ts_ms": None if pressure is None else pressure.recv_ts_ms,
        "order_pressure_age_seconds": (
            None if book_age_ms is None else max(0.0, book_age_ms / 1_000.0)
        ),
        "maximum_order_pressure_age_seconds": _MAXIMUM_BOOK_AGE_MS / 1_000,
        "opi_execution_gate": True,
        "opi_alignment_rule": "side_adjusted_order_pressure_above_zero",
        "fixed_horizon_seconds": _FIXED_HOLD_MS / 1_000,
        "minimum_entry_spacing_seconds": _REARM_MS / 1_000,
        "exit_policy": "fixed_60m",
        "last_candidate_available_time_ms": last_available_ms,
        "next_candidate_available_time_ms": (
            None if last_available_ms is None else last_available_ms + _REARM_MS
        ),
        "observed_at_ms": observed_ms,
    }
    all_met = exact and fresh and book_fresh and aligned and rearmed
    return SignalReadiness(
        side=source.readiness.side,
        conditions_met=sum((exact, fresh, book_fresh, aligned, rearmed)),
        conditions_required=5,
        blockers=() if all_met else (reason,),
        indicators=(
            f"EXACT HOURLY CROSS BLOCKER {'YES' if exact else 'NO'}",
            f"ENTRY AGE {max(0.0, age_ms / 1_000.0):.0f}s / 60s",
            f"L2 OPI {_metric(directional_opi)} {'ALIGNED' if aligned else 'BLOCKED'}",
            f"L2 AGE {_metric_seconds(book_age_ms)} / 30s",
            f"75M ENTRY REARM {'READY' if rearmed else 'WAIT'}",
            "EXIT FIXED 60M",
        ),
        metrics=metrics,
    )


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    if evaluation.side not in {"long", "short"}:
        raise ValueError("eligible SOL aligned-range candidate lacks a side")
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol="SOL",
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"sol_exact_hourly_blocker_opi_aligned_fixed60:{evaluation.side}",
    )


def _complete_tail_lines(path: Path) -> tuple[bytes, ...]:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        start = max(0, size - _TAIL_BYTES)
        handle.seek(start)
        data = handle.read()
    if not data:
        return ()
    if not data.endswith(b"\n"):
        data = data.rsplit(b"\n", 1)[0] + b"\n" if b"\n" in data else b""
    lines = data.splitlines()
    return tuple(lines[1:] if start > 0 and lines else lines)


def _json_object(line: bytes) -> dict[str, object]:
    try:
        value = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SOL asset ledger contains malformed complete JSONL") from exc
    if not isinstance(value, dict):
        raise ValueError("SOL asset ledger row must be an object")
    return value


def _order_pressure(row: dict[str, object]) -> OrderPressureObservation:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("SOL book observation payload must be an object")
    if payload.get("source") != _BOOK_SOURCE:
        raise ValueError("SOL order pressure must come from Hyperliquid mainnet L2")
    recv_ts_ms = payload.get("recv_ts_ms")
    opi = payload.get("opi")
    if isinstance(opi, bool) or not isinstance(opi, (int, float)):
        raise ValueError("SOL book observation opi must be numeric")
    if isinstance(recv_ts_ms, bool) or not isinstance(recv_ts_ms, int):
        raise ValueError("SOL book observation recv_ts_ms must be an integer")
    return OrderPressureObservation(recv_ts_ms=recv_ts_ms, opi=float(opi))


def _aware_timestamp_ms(value: pd.Timestamp) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)


def _boundary(value: int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("after_decision_time_ms must be a nonnegative integer")
    return value


def _metric(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f}"


def _metric_seconds(value_ms: int | None) -> str:
    return "N/A" if value_ms is None else f"{max(0.0, value_ms / 1_000.0):.0f}s"
