"""Frozen contract for five-minute liquidity sweep/reclaim research."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class LiquiditySweepConfig:
    """Causal event, structural barrier, and friction assumptions."""

    symbols: tuple[str, ...] = ("BTC", "SOL")
    bar_minutes: int = 5
    warmup_minutes: int = 10_080
    structure_lookback_bars: int = 12
    reward_risk_multiple: float = 2.0
    maximum_hold_bars: int = 72
    fee_bps_per_side: float = 4.5
    slippage_bps_per_side: float = 2.0
    nominal_round_trip_cost_bps: float = 13.0
    stress_round_trip_cost_bps: float = 20.0
    report_only: bool = True
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject malformed or internally inconsistent assumptions."""
        if self.symbols != ("BTC", "SOL"):
            raise ValueError("liquidity sweep symbols must equal BTC and SOL")
        _positive_integer(self.bar_minutes, "bar_minutes")
        _positive_integer(self.warmup_minutes, "warmup_minutes")
        _positive_integer(self.structure_lookback_bars, "structure_lookback_bars")
        _positive(self.reward_risk_multiple, "reward_risk_multiple")
        _positive_integer(self.maximum_hold_bars, "maximum_hold_bars")
        _non_negative(self.fee_bps_per_side, "fee_bps_per_side")
        _non_negative(self.slippage_bps_per_side, "slippage_bps_per_side")
        expected = 2.0 * (self.fee_bps_per_side + self.slippage_bps_per_side)
        if not math.isclose(self.nominal_round_trip_cost_bps, expected, abs_tol=1e-12):
            raise ValueError("nominal round-trip cost identity is inconsistent")
        if self.stress_round_trip_cost_bps < self.nominal_round_trip_cost_bps:
            raise ValueError("stress cost must not be below nominal cost")
        if not self.report_only or self.execution_authority != "none":
            raise ValueError("liquidity sweep research must remain report-only")

    @property
    def maximum_hold_minutes(self) -> int:
        """Return the fixed six-hour horizon in minutes."""
        return self.bar_minutes * self.maximum_hold_bars

    @property
    def stress_haircut_bps(self) -> float:
        """Return stress friction in excess of nominal friction."""
        return self.stress_round_trip_cost_bps - self.nominal_round_trip_cost_bps


def _positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be positive and finite")


def _non_negative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be non-negative and finite")


def _positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
