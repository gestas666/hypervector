"""Execution-incapable SOL canary account and venue preflight report."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from hypervector.live.hyperliquid_protocol import (
    SolBookSnapshot,
    SolFundingPayment,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig


class SolReadOnlyReaderProtocol(Protocol):
    """Read surface required to prove canary state without execution authority."""

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight: ...

    def reconcile(self) -> SolReconciliationSnapshot: ...

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot: ...

    def funding_payments(
        self,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[SolFundingPayment, ...]: ...


def collect_sol_read_only_preflight(
    *,
    config: SolRangeOnsetConfig,
    reader: SolReadOnlyReaderProtocol,
    observed_at: datetime,
) -> dict[str, object]:
    """Collect sanitized venue facts and explicit technical readiness evidence."""
    if observed_at.tzinfo is None:
        raise ValueError("preflight observed_at must be timezone-aware")
    now = observed_at.astimezone(UTC)
    venue = reader.preflight(expected_max_leverage=int(config.venue_max_leverage))
    reconciliation = reader.reconcile()
    book = reader.book_snapshot(depth_levels=5)
    end_ms = int(now.timestamp() * 1_000)
    start_ms = int((now - timedelta(hours=24)).timestamp() * 1_000)
    funding = reader.funding_payments(start_time_ms=start_ms, end_time_ms=end_ms)
    planned_notional = min(
        reconciliation.account.account_value_usd
        * config.margin_fraction
        * config.leverage,
        config.max_notional_usd,
    )
    minimum_notional = venue.mark_price * venue.size_step
    reasons = _readiness_reasons(reconciliation, planned_notional, minimum_notional)
    return {
        "schema_version": 1,
        "observed_at_utc": now.isoformat(),
        "identity": _identity(config),
        "authority": _authority(),
        "venue": _venue_payload(venue, book),
        "account": _account_payload(reconciliation, funding),
        "canary": _canary_payload(config, planned_notional, minimum_notional, reasons),
    }


def _identity(config: SolRangeOnsetConfig) -> dict[str, object]:
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "symbol": config.symbol,
        "network": config.network,
    }


def _authority() -> dict[str, object]:
    return {
        "execution_authority": "none",
        "execution_client_constructed": False,
        "signing_key_required": False,
        "operation": "read_only_preflight",
    }


def _venue_payload(
    preflight: SolVenuePreflight,
    book: SolBookSnapshot,
) -> dict[str, object]:
    return {
        "account_abstraction_mode": preflight.account_abstraction_mode,
        "mark_price": preflight.mark_price,
        "size_decimals": preflight.market.size_decimals,
        "size_step": preflight.size_step,
        "price_tick": preflight.price_tick,
        "max_leverage": preflight.market.max_leverage,
        "maker_rate": preflight.fees.maker_rate,
        "taker_rate": preflight.fees.taker_rate,
        "book_timestamp_ms": book.exchange_timestamp_ms,
        "spread_bps": book.spread_bps,
        "bid_depth_sol": book.bid_depth,
        "ask_depth_sol": book.ask_depth,
        "order_pressure": book.order_pressure,
    }


def _account_payload(
    reconciliation: SolReconciliationSnapshot,
    funding: tuple[SolFundingPayment, ...],
) -> dict[str, object]:
    account = reconciliation.account
    return {
        "account_value_usd": account.account_value_usd,
        "withdrawable_usd": account.withdrawable_usd,
        "total_margin_used_usd": account.total_margin_used_usd,
        "total_notional_position_usd": account.total_notional_position_usd,
        "sol_position_size": account.position.size_signed,
        "sol_liquidation_price": account.position.liquidation_price,
        "sol_open_orders": len(reconciliation.open_orders),
        "recent_sol_fills": len(reconciliation.fills),
        "funding_24h_usd": sum(item.usdc_delta for item in funding),
        "funding_events_24h": len(funding),
        "flat": reconciliation.is_flat,
    }


def _canary_payload(
    config: SolRangeOnsetConfig,
    planned_notional: float,
    minimum_notional: float,
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "reference_equity_usd": config.initial_shadow_equity_usd,
        "margin_fraction": config.margin_fraction,
        "leverage": config.leverage,
        "max_notional_usd": config.max_notional_usd,
        "planned_notional_usd": planned_notional,
        "minimum_lot_notional_usd": minimum_notional,
        "stop_bps": config.stop_bps,
        "maximum_hold_seconds": config.maximum_hold_seconds,
        "metalabel_mode": config.metalabel_mode,
        "technically_ready": not reasons,
        "readiness_reasons": reasons,
    }


def _readiness_reasons(
    reconciliation: SolReconciliationSnapshot,
    planned_notional: float,
    minimum_notional: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not reconciliation.is_flat:
        reasons.append("SOL account is not flat or has open SOL orders")
    if reconciliation.account.account_value_usd <= 0.0:
        reasons.append("account value is not positive")
    if planned_notional < minimum_notional:
        reasons.append("planned canary notional is below one SOL lot")
    return tuple(reasons)
