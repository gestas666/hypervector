"""Typed contracts for causal report-only HIP-3 shadow lifecycles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal

from hypervector.cohort_profit_lock_policy import ProfitLockPolicy, policy_declaration
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)

LifecycleSide = Literal["long", "short"]
LifecycleExitReason = Literal[
    "stop",
    "signal",
    "opposite_strategy_intent",
    "profit_lock",
    "max_hold",
]


@dataclass(frozen=True)
class Hip3ShadowLifecycleConfig:
    """Frozen route, cost, size, and causal timing assumptions."""

    symbol: str
    provider_id: str
    profile_id: str
    ledger_profile_id: str
    signal_config: Hip3BreakoutPressureConfig
    fee_bps_per_side: float
    residual_latency_bps_per_side: float
    stress_extra_bps_per_side: float
    notional_usd: float
    maximum_book_lateness_ms: int
    maximum_mark_gap_ms: int
    maximum_hold_minutes: int
    friction_source: str
    entry_sides: frozenset[LifecycleSide] = frozenset({"long", "short"})
    fixed_stop_bps: float | None = None
    signal_exit_enabled: bool = True
    opposite_entry_exit_enabled: bool = False
    profit_lock_policy: ProfitLockPolicy | None = None
    execution_profile_id: str | None = None
    execution_profile_fingerprint: str | None = None

    def __post_init__(self) -> None:
        """Reject aliased identities and unsupported lifecycle assumptions."""
        _route_identity(self)
        _nonnegative(self.fee_bps_per_side, "fee")
        _nonnegative(self.residual_latency_bps_per_side, "latency")
        _nonnegative(self.stress_extra_bps_per_side, "stress")
        _positive(self.notional_usd, "notional")
        _positive_integer(self.maximum_book_lateness_ms, "maximum book lateness")
        _positive_integer(self.maximum_mark_gap_ms, "maximum mark gap")
        if self.maximum_hold_minutes != 1_440:
            raise ValueError("HIP-3 lifecycle maximum hold must equal 24 hours")
        if not self.friction_source:
            raise ValueError("HIP-3 lifecycle friction source is required")
        if not self.entry_sides or not self.entry_sides.issubset({"long", "short"}):
            raise ValueError("HIP-3 lifecycle entry sides must be long and/or short")
        if self.fixed_stop_bps is not None:
            _positive(self.fixed_stop_bps, "fixed stop")
        if not isinstance(self.signal_exit_enabled, bool):
            raise ValueError("HIP-3 lifecycle signal-exit flag must be boolean")
        if not isinstance(self.opposite_entry_exit_enabled, bool):
            raise ValueError("HIP-3 lifecycle opposite-entry exit flag must be boolean")
        if self.profit_lock_policy is not None:
            policy_declaration(self.profit_lock_policy)
        _execution_identity(
            self.execution_profile_id, self.execution_profile_fingerprint
        )


@dataclass(frozen=True)
class Hip3ShadowLifecycle:
    """One technically resolved prospective route lifecycle."""

    side: LifecycleSide
    decision_time_ms: int
    signal_available_time_ms: int
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    exit_price: float
    stop_price: float
    stop_trigger_time_ms: int | None
    exit_reason: LifecycleExitReason
    quantity: float
    notional_usd: float
    gross_pnl_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    modeled_friction_usd: float
    net_pnl_usd: float
    gross_return_bps: float
    net_return_bps: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe immutable lifecycle record."""
        return asdict(self)


@dataclass(frozen=True)
class Hip3ShadowCensoredLifecycle:
    """One onset that cannot support a complete economic claim."""

    side: LifecycleSide
    decision_time_ms: int
    reason: str
    entry_time_ms: int | None = None
    route_state_resolved_time_ms: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe censored lifecycle record."""
        return asdict(self)


def _route_identity(config: Hip3ShadowLifecycleConfig) -> None:
    if not config.symbol.startswith("xyz:"):
        raise ValueError("HIP-3 lifecycle identity requires an exact xyz symbol")
    token = config.symbol.removeprefix("xyz:").lower()
    identities = (config.provider_id, config.profile_id, config.ledger_profile_id)
    if any(not value or token not in value.lower() for value in identities):
        raise ValueError("HIP-3 lifecycle route identity is inconsistent")


def _positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"HIP-3 lifecycle {label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"HIP-3 lifecycle {label} must be finite and nonnegative")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"HIP-3 lifecycle {label} must be a positive integer")


def _execution_identity(profile_id: str | None, fingerprint: str | None) -> None:
    if profile_id is None and fingerprint is None:
        return
    valid = (
        isinstance(profile_id, str)
        and bool(profile_id.strip())
        and isinstance(fingerprint, str)
        and len(fingerprint) == 64
        and all(character in "0123456789abcdef" for character in fingerprint)
    )
    if not valid:
        raise ValueError("HIP-3 lifecycle execution profile identity is incomplete")
