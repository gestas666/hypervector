"""Frozen contract for venue-native one-minute order-flow impulse research."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class OrderFlowImpulseConfig:
    """Causal timing, event, barrier, and friction assumptions."""

    symbols: tuple[str, ...] = ("BTC", "SOL")
    warmup_minutes: int = 10_080
    return_quantile: float = 0.90
    volume_quantile: float = 0.75
    l2_votes_required: int = 2
    target_bps: float = 30.0
    stop_bps: float = 20.0
    maximum_hold_minutes: int = 15
    fee_bps_per_side: float = 4.5
    slippage_bps_per_side: float = 2.0
    nominal_round_trip_cost_bps: float = 13.0
    stress_round_trip_cost_bps: float = 20.0
    report_only: bool = True
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject malformed or internally inconsistent research assumptions."""
        if self.symbols != ("BTC", "SOL"):
            raise ValueError("order-flow impulse symbols must equal BTC and SOL")
        if isinstance(self.warmup_minutes, bool) or self.warmup_minutes <= 0:
            raise ValueError("order-flow impulse warmup must be positive")
        _validate_quantile(self.return_quantile, "return_quantile")
        _validate_quantile(self.volume_quantile, "volume_quantile")
        if self.l2_votes_required not in (1, 2, 3):
            raise ValueError("L2 votes required must be one, two, or three")
        _positive(self.target_bps, "target_bps")
        _positive(self.stop_bps, "stop_bps")
        if self.maximum_hold_minutes <= 0:
            raise ValueError("maximum hold must be positive")
        _non_negative(self.fee_bps_per_side, "fee_bps_per_side")
        _non_negative(self.slippage_bps_per_side, "slippage_bps_per_side")
        expected = 2.0 * (self.fee_bps_per_side + self.slippage_bps_per_side)
        if not math.isclose(self.nominal_round_trip_cost_bps, expected, abs_tol=1e-12):
            raise ValueError("nominal round-trip cost identity is inconsistent")
        if self.stress_round_trip_cost_bps < self.nominal_round_trip_cost_bps:
            raise ValueError("stress cost must not be below nominal cost")
        if not self.report_only or self.execution_authority != "none":
            raise ValueError("order-flow impulse research must remain report-only")

    @property
    def stress_haircut_bps(self) -> float:
        """Return the additional cost applied to nominal net outcomes."""
        return self.stress_round_trip_cost_bps - self.nominal_round_trip_cost_bps


def default_orderflow_impulse_config() -> OrderFlowImpulseConfig:
    """Return the registered one-minute development protocol."""
    return OrderFlowImpulseConfig()


def _validate_quantile(value: float, name: str) -> None:
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise ValueError(f"{name} must be strictly between zero and one")


def _positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be positive and finite")


def _non_negative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be non-negative and finite")
