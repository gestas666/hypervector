"""Validation and projection helpers for the shared live cohort runner."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    PositionState,
)
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.multi_asset_cohort_telemetry import (
    AssetCohortSnapshot,
    SharedAccountFacts,
)
from hypervector.live.perp_venue_identity import parse_perp_venue_identity
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState
from hypervector.live.sol_protective_order import protective_stop_covers


class MultiAssetLiveRunnerError(RuntimeError):
    """The cohort cannot preserve causal shared-account execution."""


class CohortDegradedBlindnessError(MultiAssetLiveRunnerError):
    """Account reconciliation has failed for longer than the wall-clock bound.

    Degraded polls append to the same ledger whose modification time is the
    supervisor's liveness probe, so an unbounded degraded loop reports a running
    backend that has not seen its account in hours. A public market-data outage
    does not count: reconciliation and the unconditional deadlines still ran
    before that read failed, and a restart would not repair it. Nor does an
    offline host or venue: when a fresh session's public read fails too, the
    runner keeps polling in place. This is a technical failure, not a strategy
    gate: it ends the process so startup reconciliation runs again, and the
    supervisor relaunches it without charging the crash budget.
    """


class ReconciliationEngine(Protocol):
    """Minimum engine surface needed by shared reconciliation helpers."""

    @property
    def snapshot(self) -> SolLiveSnapshot: ...

    def reconcile_telemetry(
        self, *, funding_start_time_ms: int, funding_end_time_ms: int
    ) -> SolReconciliationSnapshot: ...


def validate_runtime(
    symbols: tuple[str, ...],
    engines: Mapping[str, object],
    router: BidirectionalIntentRouter,
    poll_seconds: float,
    maximum_holds: Mapping[str, int],
    execution_contracts: Mapping[str, ProviderExecutionContract],
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
    provider_entry_sizing: Mapping[tuple[str, str], CohortEntrySizing],
    provider_directional_entry_sizing: Mapping[tuple[str, str, str], CohortEntrySizing],
) -> None:
    """Reject incomplete runner ownership and execution configuration."""
    if not symbols or len(set(symbols)) != len(symbols):
        raise MultiAssetLiveRunnerError("runner symbols must be unique and non-empty")
    if set(engines) != set(symbols) or router.symbols != symbols:
        raise MultiAssetLiveRunnerError("engines, router, and symbols must agree")
    if not math.isfinite(poll_seconds) or poll_seconds <= 0.0:
        raise MultiAssetLiveRunnerError("poll_seconds must be positive and finite")
    _validate_holds(symbols, maximum_holds)
    _validate_provider_contracts(symbols, execution_contracts, executable_pairs)
    if not set(provider_entry_sizing).issubset(executable_pairs):
        raise MultiAssetLiveRunnerError(
            "provider entry sizing exceeds executable provider-symbol scope"
        )
    if not set(provider_directional_entry_sizing).issubset(executable_directions):
        raise MultiAssetLiveRunnerError(
            "provider directional entry sizing exceeds executable direction scope"
        )


def entry_provider_strategy_id(strategy_id: str) -> str:
    """Recover the selected provider from a manual-entry attribution id."""
    prefix = "operator_override:"
    return strategy_id.removeprefix(prefix) if strategy_id.startswith(prefix) else strategy_id


def shared_account_facts(
    symbols: tuple[str, ...],
    venues: tuple[SolReconciliationSnapshot, ...],
) -> SharedAccountFacts:
    """Project shared equity and one exposure total per perp namespace."""
    if not venues:
        raise MultiAssetLiveRunnerError("shared account reconciliation is empty")
    if len(symbols) != len(venues):
        raise MultiAssetLiveRunnerError("shared account symbols and venue snapshots must agree")
    namespaces: dict[str, SolReconciliationSnapshot] = {}
    for symbol, venue in zip(symbols, venues, strict=True):
        namespace = parse_perp_venue_identity(symbol).perp_dex
        namespaces[namespace] = venue
    account = venues[-1].account
    return SharedAccountFacts(
        account.account_value_usd,
        account.withdrawable_usd,
        sum(value.account.total_margin_used_usd for value in namespaces.values()),
        sum(value.account.total_notional_position_usd for value in namespaces.values()),
        account.balance_source,
    )


def reconcile_engines(
    symbols: tuple[str, ...],
    engines: Mapping[str, ReconciliationEngine],
    funding_start_time_ms: int,
    funding_end_time_ms: int,
) -> tuple[SolReconciliationSnapshot, ...]:
    """Reconcile every symbol against one exact shared funding window."""
    return tuple(
        engines[symbol].reconcile_telemetry(
            funding_start_time_ms=funding_start_time_ms,
            funding_end_time_ms=funding_end_time_ms,
        )
        for symbol in symbols
    )


def asset_snapshots(
    symbols: tuple[str, ...],
    engines: Mapping[str, ReconciliationEngine],
    venues: tuple[SolReconciliationSnapshot, ...],
    reference_prices: Mapping[str, float],
) -> tuple[AssetCohortSnapshot, ...]:
    """Project each reconciled venue using its corresponding engine state."""
    return tuple(
        asset_snapshot(symbol, engines[symbol].snapshot, venue, reference_prices.get(symbol))
        for symbol, venue in zip(symbols, venues, strict=True)
    )


def engine_position_states(
    symbols: tuple[str, ...], engines: Mapping[str, ReconciliationEngine]
) -> dict[str, PositionState]:
    """Return deterministic router position states from signed engine sizes."""
    return {
        symbol: PositionState(
            symbol,
            position_side(engines[symbol].snapshot.position_size_signed),
        )
        for symbol in symbols
    }


def asset_snapshot(
    symbol: str,
    snapshot: SolLiveSnapshot,
    venue: SolReconciliationSnapshot,
    mark_price: float | None,
) -> AssetCohortSnapshot:
    """Combine lifecycle identity with venue-authoritative position facts."""
    position = venue.position
    venue_mark = _venue_synchronous_mark(
        position.size_signed,
        position.position_value_usd,
        mark_price,
    )
    return AssetCohortSnapshot(
        symbol=symbol,
        state=snapshot.state.value,
        position_size_signed=snapshot.position_size_signed,
        entry_oid=snapshot.entry_oid,
        stop_oid=snapshot.stop_oid,
        last_fault=snapshot.last_fault,
        mark_price=venue_mark,
        entry_price=position.entry_price,
        liquidation_price=position.liquidation_price,
        margin_used_usd=position.margin_used_usd,
        position_value_usd=position.position_value_usd,
        unrealized_pnl_usd=position.unrealized_pnl_usd,
        leverage=position.leverage,
        target_oid=snapshot.target_oid,
        target_price=snapshot.target_price,
        execution_plan=snapshot.execution_plan,
        market_reference_price=mark_price,
        opened_at_ms=snapshot.opened_at_ms,
        protective_exit_pending=snapshot.protective_progress.stop_exit_required,
        partial_exit_fill_count=len(snapshot.protective_progress.fills),
        partial_exit_size=math.fsum(fill.size for fill in snapshot.protective_progress.fills),
        stop_protection=_stop_protection(snapshot, venue),
    )


def _stop_protection(snapshot: SolLiveSnapshot, venue: SolReconciliationSnapshot) -> str:
    if venue.position.size_signed == 0.0:
        return "flat"
    stops = [order for order in venue.open_orders if order.oid == snapshot.stop_oid]
    if len(stops) == 1 and protective_stop_covers(stops[0], venue.position.size_signed):
        return "covering"
    return "missing"


def _venue_synchronous_mark(
    size_signed: float,
    position_value_usd: float,
    market_reference_price: float | None,
) -> float | None:
    """Derive a mark sharing the venue position snapshot's timestamp."""
    if size_signed == 0.0 or position_value_usd <= 0.0:
        return market_reference_price
    return position_value_usd / abs(size_signed)


def position_side(size: float) -> str | None:
    """Return one canonical direction from signed venue size."""
    if size > 0.0:
        return "long"
    if size < 0.0:
        return "short"
    return None


def aware(value: datetime) -> datetime:
    """Require a timezone-aware cohort clock value."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise MultiAssetLiveRunnerError("cohort clock must be timezone-aware")
    return value


def validate_max_polls(value: int | None) -> None:
    """Reject invalid bounded-run counts."""
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
        raise MultiAssetLiveRunnerError("max_polls must be a positive integer")


def remaining_delay(period_seconds: float, elapsed_seconds: float) -> float:
    """Preserve a start-to-start polling period."""
    if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0.0:
        raise MultiAssetLiveRunnerError("monotonic cycle duration is invalid")
    return max(0.0, period_seconds - elapsed_seconds)


def all_flat_and_unowned(snapshots: tuple[SolLiveSnapshot, ...]) -> bool:
    """Return whether every lifecycle is flat without an owned order identity."""
    for snapshot in snapshots:
        owned = (
            snapshot.entry_oid,
            snapshot.stop_oid,
            snapshot.target_oid,
            snapshot.close_oid,
        )
        if snapshot.state != SolLiveState.FLAT or any(oid is not None for oid in owned):
            return False
        if snapshot.position_size_signed != 0.0:
            return False
    return True


def _validate_holds(symbols: tuple[str, ...], values: Mapping[str, int]) -> None:
    if set(values) != set(symbols):
        raise MultiAssetLiveRunnerError("maximum holds must cover every symbol")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in values.values()
    ):
        raise MultiAssetLiveRunnerError("maximum holds must be positive seconds")


def _validate_provider_contracts(
    symbols: tuple[str, ...],
    contracts: Mapping[str, ProviderExecutionContract],
    pairs: frozenset[tuple[str, str]],
) -> None:
    if not pairs:
        raise MultiAssetLiveRunnerError("runner requires an executable provider pair")
    provider_ids = {strategy for strategy, _ in pairs}
    if not provider_ids.issubset(contracts):
        raise MultiAssetLiveRunnerError("executable providers require execution contracts")
    if any(symbol not in symbols for _, symbol in pairs):
        raise MultiAssetLiveRunnerError("executable provider pairs reference an unknown symbol")
