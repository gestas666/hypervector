"""Models and validation primitives for BRENTOIL shadow lifecycles."""

from __future__ import annotations

from dataclasses import dataclass
import math

from hypervector.live.brentoil_oil_shock_shadow import (
    BRENTOIL_OIL_SHOCK_PROFILE_ID,
    BRENTOIL_OIL_SHOCK_PROVIDER_ID,
    BRENTOIL_OIL_SHOCK_SYMBOL,
)
from hypervector.live.brentoil_oil_shock_shadow_runner import (
    BRENTOIL_OIL_SHOCK_LEDGER_PROFILE_ID,
)


@dataclass(frozen=True)
class BrentoilOilShockLifecycleConfig:
    """Frozen execution-cost and strategy-exit measurement contract."""

    fee_bps_per_side: float
    nominal_residual_bps_per_side: float
    stress_residual_bps_per_side: float
    notional_usd: float
    maximum_book_lateness_ms: int
    maximum_mark_gap_ms: int
    target_bps: float
    stop_bps: float
    maximum_hold_ms: int
    friction_source: str

    def __post_init__(self) -> None:
        """Reject malformed costs, barriers, or timing assumptions."""
        self._validate_costs()
        self._validate_strategy()

    def _validate_costs(self) -> None:
        for label, value in (
            ("fee", self.fee_bps_per_side),
            ("nominal residual", self.nominal_residual_bps_per_side),
            ("stress residual", self.stress_residual_bps_per_side),
        ):
            nonnegative_number(value, label)
        if self.stress_residual_bps_per_side < self.nominal_residual_bps_per_side:
            raise ValueError("BRENTOIL lifecycle stress cannot be below nominal")

    def _validate_strategy(self) -> None:
        for label, value in (
            ("notional", self.notional_usd),
            ("target", self.target_bps),
            ("stop", self.stop_bps),
        ):
            positive_number(value, label)
        for label, value in (
            ("maximum book lateness", self.maximum_book_lateness_ms),
            ("maximum mark gap", self.maximum_mark_gap_ms),
            ("maximum hold", self.maximum_hold_ms),
        ):
            positive_integer(value, label)
        if self.target_bps <= self.stop_bps or not self.friction_source:
            raise ValueError("BRENTOIL lifecycle strategy contract is invalid")

    @property
    def symbol(self) -> str:
        """Return the exact venue symbol."""
        return BRENTOIL_OIL_SHOCK_SYMBOL

    @property
    def provider_id(self) -> str:
        """Return the frozen shadow provider identity."""
        return BRENTOIL_OIL_SHOCK_PROVIDER_ID

    @property
    def profile_id(self) -> str:
        """Return the frozen shadow profile identity."""
        return BRENTOIL_OIL_SHOCK_PROFILE_ID

    @property
    def ledger_profile_id(self) -> str:
        """Return the exact REST book-ledger identity."""
        return BRENTOIL_OIL_SHOCK_LEDGER_PROFILE_ID


@dataclass(frozen=True)
class Mark:
    """Exact receipt-time mark observation."""

    timestamp_ms: int
    price: float


@dataclass(frozen=True)
class Fill:
    """Finite-depth modeled fill."""

    timestamp_ms: int
    price: float
    quantity: float
    quote_usd: float


@dataclass(frozen=True)
class ExitEvent:
    """First causally observed exit trigger."""

    reason: str
    timestamp_ms: int


@dataclass(frozen=True)
class Lifecycle:
    """Resolved prospective lifecycle excluding funding."""

    side: str
    decision_time_ms: int
    signal_available_time_ms: int
    entry_time_ms: int
    exit_trigger_time_ms: int
    exit_time_ms: int
    exit_reason: str
    entry_price: float
    exit_price: float
    target_price: float
    stop_price: float
    quantity: float
    notional_usd: float
    gross_pnl_usd: float
    fees_usd: float
    modeled_residual_friction_usd: float
    modeled_net_usd_excluding_funding: float
    modeled_net_return_bps_excluding_funding: float


def positive_number(value: object, label: str) -> float:
    """Return a finite positive number or fail closed."""
    number = nonnegative_number(value, label)
    if number == 0.0:
        raise ValueError(f"BRENTOIL lifecycle {label} must be positive")
    return number


def nonnegative_number(value: object, label: str) -> float:
    """Return a finite nonnegative number or fail closed."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"BRENTOIL lifecycle {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"BRENTOIL lifecycle {label} must be finite and nonnegative")
    return number


def positive_integer(value: object, label: str) -> int:
    """Return a positive integer or fail closed."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"BRENTOIL lifecycle {label} must be a positive integer")
    return value
