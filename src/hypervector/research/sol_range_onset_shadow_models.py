"""Typed configuration and state models for SOL range-onset shadowing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Literal

from hypervector.research.range_onset_event_models import EventExitReason, EventSignal
from hypervector.research.shared_portfolio_models import Direction

ShadowStatus = Literal["active", "evidence_failed"]


@dataclass(frozen=True)
class SolShadowConfig:
    """Frozen sizing, venue, fee, stop, and evidence assumptions."""

    initial_shared_equity_usd: float = 15_000.0
    capital_base_cap_usd: float = 15_000.0
    notional_cap_usd: float = 2_250.0
    margin_fraction: float = 0.03
    leverage: float = 5.0
    venue_max_leverage: float = 20.0
    stop_bps: float = 60.0
    taker_fee_rate: float = 0.00045
    max_hold_ms: int = 48 * 60 * 60 * 1_000
    capital_freshness_ms: int = 120_000

    def __post_init__(self) -> None:
        """Reject non-finite or venue-incompatible shadow assumptions."""
        for name in (
            "initial_shared_equity_usd",
            "capital_base_cap_usd",
            "notional_cap_usd",
            "margin_fraction",
            "leverage",
            "venue_max_leverage",
            "stop_bps",
        ):
            _positive(float(getattr(self, name)), name)
        if self.margin_fraction > 1.0:
            raise ValueError("margin_fraction must not exceed one")
        if self.leverage > self.venue_max_leverage:
            raise ValueError("leverage must not exceed venue_max_leverage")
        _rate(self.taker_fee_rate, "taker_fee_rate")
        _positive_integer(self.max_hold_ms, "max_hold_ms")
        _positive_integer(self.capital_freshness_ms, "capital_freshness_ms")

    @property
    def fingerprint(self) -> str:
        """Return a stable identity for restart compatibility checks."""
        payload = json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SharedCapitalSnapshot:
    """Latest BTC-authoritative equity and reserved-margin observation."""

    observed_time_ms: int
    equity_usd: float
    reserved_margin_usd: float
    source_run_id: str

    def __post_init__(self) -> None:
        """Reject unusable shared-capital telemetry."""
        _positive_integer(self.observed_time_ms, "observed_time_ms")
        _positive(self.equity_usd, "equity_usd")
        _nonnegative(self.reserved_margin_usd, "reserved_margin_usd")
        if not self.source_run_id.strip():
            raise ValueError("source_run_id must be non-empty")


@dataclass(frozen=True)
class SolShadowPosition:
    """One open hypothetical SOL position backed by visible venue depth."""

    direction: Direction
    entry_decision_time_ms: int
    entry_time_ms: int
    entry_price: float
    reference_price: float
    quantity: float
    notional_usd: float
    margin_usd: float
    entry_fee_usd: float
    stop_price: float
    liquidation_price: float
    funding_cashflow_usd: float = 0.0


@dataclass(frozen=True)
class SolShadowTrade:
    """One completed finite-depth SOL shadow lifecycle."""

    direction: Direction
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float
    exit_reason: EventExitReason


@dataclass(frozen=True)
class SolShadowSnapshot:
    """Current no-submit SOL state for persistence and telemetry."""

    status: ShadowStatus
    sol_realized_delta_usd: float
    position: SolShadowPosition | None
    pending_entry: EventSignal | None
    pending_exit_reason: EventExitReason | None
    pending_reversal: EventSignal | None
    completed_trades: tuple[SolShadowTrade, ...]


def _positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")


def _nonnegative(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be non-negative and finite")


def _rate(value: float, label: str) -> None:
    _nonnegative(value, label)
    if value >= 1.0:
        raise ValueError(f"{label} must be below one")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
