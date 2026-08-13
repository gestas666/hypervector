"""Validated identity and economics values for profit-lock lifecycle evidence."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.research.cohort_lifecycle_evidence import (
    SIZE_TOLERANCE,
    FillAggregate,
    funding_sum,
    positive_int,
    positive_number,
    required_fill,
)
from hypervector.research.cohort_live_audit_values import number, text
from hypervector.research.cohort_profit_lock_policy import CandleLike
from hypervector.research.cohort_profit_lock_results import ProfitLockEconomics

Record = Mapping[str, object]
Identity = tuple[str, str, str, str, str, str]

_MINUTE_MS = 60_000
_MONEY_TOLERANCE = 0.000_005


def lifecycle_identity(trade: Record) -> Identity:
    """Validate and return one reflected trade's immutable lifecycle identity."""
    lifecycle = text(trade.get("lifecycle_id"), "trade lifecycle")
    symbol = text(trade.get("symbol"), "trade symbol")
    strategy = text(trade.get("strategy_id"), "trade strategy")
    side = text(trade.get("side"), "trade side")
    run_id = text(trade.get("source_run_id"), "trade source run")
    profile = text(trade.get("source_profile_fingerprint"), "trade source profile")
    entry_oid = positive_int(trade.get("entry_oid"), "trade entry oid")
    if side not in {"long", "short"} or lifecycle != f"{symbol}:{entry_oid}":
        raise ValueError("profit-lock trade identity or side is inconsistent")
    return lifecycle, symbol, strategy, side, run_id, profile


def lifecycle_economics(
    trade: Record,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[int, float],
) -> ProfitLockEconomics:
    """Reconcile venue fills, funding, and recorded net lifecycle economics."""
    symbol = text(trade.get("symbol"), "trade symbol")
    entry = _record(trade.get("entry"), "trade entry")
    exit_leg = _record(trade.get("exit"), "trade exit")
    entry_oid = positive_int(trade.get("entry_oid"), "trade entry oid")
    exit_oid = positive_int(trade.get("exit_oid"), "trade exit oid")
    entry_fill = required_fill(
        fills, (symbol, entry_oid), entry, "entry", "profit-lock"
    )
    exit_fill = required_fill(
        fills, (symbol, exit_oid), exit_leg, "exit", "profit-lock"
    )
    values = _economics_values(trade, entry, exit_leg, entry_fill, exit_fill, funding)
    return ProfitLockEconomics(*values)


def completed_bars(
    candles: Mapping[int, CandleLike],
    entry_ms: int,
    exit_ms: int,
) -> tuple[tuple[int, ...], tuple[CandleLike, ...]]:
    """Return the complete expected minute grid and bars present on that grid."""
    first = ((entry_ms + _MINUTE_MS - 1) // _MINUTE_MS) * _MINUTE_MS
    last = ((exit_ms - _MINUTE_MS) // _MINUTE_MS) * _MINUTE_MS
    expected = (
        () if last < first else tuple(range(first, last + _MINUTE_MS, _MINUTE_MS))
    )
    observed = tuple(
        candles[timestamp] for timestamp in expected if timestamp in candles
    )
    return expected, observed


def lifecycle_payload(
    identity: Identity,
    economics: ProfitLockEconomics,
    status: str,
    policies: Mapping[str, object],
    *,
    expected: int | None = None,
    observed: int | None = None,
) -> dict[str, object]:
    """Build one normalized lifecycle result without changing trading authority."""
    return {
        "status": status,
        "lifecycle_id": identity[0],
        "symbol": identity[1],
        "strategy_id": identity[2],
        "side": identity[3],
        "source_run_id": identity[4],
        "source_profile_fingerprint": identity[5],
        "exit_timestamp_ms": economics.exit_timestamp_ms,
        "completed_bars_expected": expected,
        "completed_bars_observed": observed,
        "entry_notional_usd": economics.entry_price * economics.size,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "policies": dict(policies),
    }


def regime_contract() -> dict[str, object]:
    """Return the immutable report-only contract for regime-conditioned evidence."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def _economics_values(
    trade: Record,
    entry: Record,
    exit_leg: Record,
    entry_fill: FillAggregate,
    exit_fill: FillAggregate,
    funding: Mapping[int, float],
) -> tuple[int, int, float, float, float, float, float, float, float, float]:
    entry_ms = _nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    exit_ms = _nonnegative_int(exit_leg.get("venue_timestamp_ms"), "exit timestamp")
    entry_price = positive_number(entry.get("price"), "entry price")
    exit_price = positive_number(exit_leg.get("price"), "exit price")
    reference = positive_number(
        exit_leg.get("expected_reference_price"), "exit reference"
    )
    size = positive_number(entry.get("size"), "entry size")
    actual_funding = number(trade.get("funding_usd"), "trade funding")
    actual_net = number(trade.get("net_pnl_usd"), "trade net PnL")
    _validate_actual_economics(
        trade,
        entry_fill,
        exit_fill,
        funding,
        entry_ms,
        exit_ms,
        entry_price,
        exit_price,
        size,
    )
    return (
        entry_ms,
        exit_ms,
        entry_price,
        exit_price,
        size,
        entry_fill.fee_usd,
        exit_fill.fee_usd / exit_fill.notional_usd,
        exit_price / reference,
        actual_funding,
        actual_net,
    )


def _validate_actual_economics(
    trade: Record,
    entry_fill: FillAggregate,
    exit_fill: FillAggregate,
    funding: Mapping[int, float],
    entry_ms: int,
    exit_ms: int,
    entry_price: float,
    exit_price: float,
    size: float,
) -> None:
    actual_funding = number(trade.get("funding_usd"), "trade funding")
    recorded_fees = number(trade.get("fees_usd"), "trade fees")
    actual_net = number(trade.get("net_pnl_usd"), "trade net PnL")
    checks = (
        math.isclose(entry_fill.size, exit_fill.size, abs_tol=SIZE_TOLERANCE),
        math.isclose(
            recorded_fees,
            entry_fill.fee_usd + exit_fill.fee_usd,
            abs_tol=_MONEY_TOLERANCE,
        ),
        math.isclose(
            actual_funding,
            funding_sum(funding, entry_ms, exit_ms),
            abs_tol=_MONEY_TOLERANCE,
        ),
        math.isfinite(actual_net),
        text(trade.get("side"), "trade side") in {"long", "short"},
        min(entry_price, exit_price, size) > 0.0,
    )
    if not all(checks):
        raise ValueError("profit-lock actual lifecycle economics do not reconcile")


def _record(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value
