"""Immutable contract for causal exact-one-blocker execution replay."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

OpiCohort = Literal["aligned", "opposed", "all"]
LiquidityPolicy = Literal["top_level", "visible_depth"]


@dataclass(frozen=True)
class OneBlockerExecutionContract:
    """Predeclared replay mechanics for one provider-symbol-blocker hypothesis."""

    strategy_id: str
    symbol: str
    blocker: str
    horizon_minutes: int
    maximum_context_age_ms: int
    maximum_entry_delay_ms: int
    maximum_exit_delay_ms: int
    notional_usd: float
    taker_fee_rate: float
    stop_proxy_bps: float
    opi_cohort: OpiCohort
    target_proxy_bps: float | None = None
    minimum_available_time_ms: int = 0
    minimum_entry_spacing_minutes: int | None = None
    liquidity_policy: LiquidityPolicy = "top_level"

    def __post_init__(self) -> None:
        """Reject malformed or success-shaped execution assumptions."""
        for value, label in (
            (self.strategy_id, "strategy id"),
            (self.symbol, "symbol"),
            (self.blocker, "blocker"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        for value, label in (
            (self.horizon_minutes, "horizon minutes"),
            (self.maximum_context_age_ms, "maximum context age"),
            (self.maximum_entry_delay_ms, "maximum entry delay"),
            (self.maximum_exit_delay_ms, "maximum exit delay"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if (
            isinstance(self.minimum_available_time_ms, bool)
            or not isinstance(self.minimum_available_time_ms, int)
            or self.minimum_available_time_ms < 0
        ):
            raise ValueError("minimum available time must be a non-negative integer")
        spacing = self.minimum_entry_spacing_minutes
        if spacing is not None and (
            isinstance(spacing, bool)
            or not isinstance(spacing, int)
            or spacing < self.horizon_minutes
        ):
            raise ValueError("minimum entry spacing must not be shorter than horizon")
        for value, label in (
            (self.notional_usd, "notional"),
            (self.stop_proxy_bps, "stop proxy"),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{label} must be positive and finite")
        if self.target_proxy_bps is not None and (
            not isfinite(self.target_proxy_bps) or self.target_proxy_bps <= 0.0
        ):
            raise ValueError("target proxy must be positive and finite when configured")
        if not isfinite(self.taker_fee_rate) or not 0.0 <= self.taker_fee_rate < 0.01:
            raise ValueError("taker fee rate must be finite and below one percent")
        if self.opi_cohort not in {"aligned", "opposed", "all"}:
            raise ValueError("OPI cohort must be aligned, opposed, or all")
        if self.liquidity_policy not in {"top_level", "visible_depth"}:
            raise ValueError("liquidity policy must be top_level or visible_depth")

    def as_payload(self) -> dict[str, object]:
        """Return the explicit immutable experiment contract."""
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "blocker": self.blocker,
            "horizon_minutes": self.horizon_minutes,
            "minimum_entry_spacing_minutes": self.entry_spacing_minutes,
            "maximum_context_age_ms": self.maximum_context_age_ms,
            "maximum_entry_delay_ms": self.maximum_entry_delay_ms,
            "maximum_exit_delay_ms": self.maximum_exit_delay_ms,
            "notional_usd": self.notional_usd,
            "taker_fee_rate": self.taker_fee_rate,
            "stop_proxy_bps": self.stop_proxy_bps,
            "target_proxy_bps": self.target_proxy_bps,
            "opi_cohort": self.opi_cohort,
            "minimum_available_time_ms": self.minimum_available_time_ms,
            "entry_rule": "first_recorded_bbo_at_or_after_routing_publication",
            "exit_rule": _exit_rule(self.target_proxy_bps),
            "liquidity_rule": _liquidity_rule(self.liquidity_policy),
            "alignment_rule": _alignment_rule(self.opi_cohort),
            "live_pnl_claimed": False,
            "simulated_execution_estimated": True,
            "execution_authority": "none",
        }

    @property
    def entry_spacing_minutes(self) -> int:
        """Return the effective accepted-entry spacing for this contract."""
        return self.minimum_entry_spacing_minutes or self.horizon_minutes


def _alignment_rule(cohort: OpiCohort) -> str:
    if cohort == "all":
        return "all_side_adjusted_routing_publication_opi"
    comparison = "above_zero" if cohort == "aligned" else "at_or_below_zero"
    return f"side_adjusted_routing_publication_opi_{comparison}"


def _exit_rule(target_proxy_bps: float | None) -> str:
    if target_proxy_bps is None:
        return "first_recorded_adverse_bbo_at_or_after_fixed_horizon"
    return "first_recorded_target_or_stop_bbo_otherwise_fixed_horizon"


def _liquidity_rule(policy: LiquidityPolicy) -> str:
    if policy == "top_level":
        return "entire_notional_visible_at_top_level"
    return "entire_notional_visible_within_recorded_depth"
