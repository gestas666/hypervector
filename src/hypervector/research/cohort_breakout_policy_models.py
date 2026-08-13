"""Validated models and disclosure contract for breakout forward evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class BreakoutPolicyForwardSpec:
    """Freeze the counterfactual breakout stop and bounded-hold contract."""

    source_strategy_id: str
    source_run_id: str
    cutoff_time_ms: int
    symbols: tuple[str, ...]
    source_execution_symbols: tuple[str, ...]
    competing_execution_providers_by_symbol: Mapping[str, tuple[str, ...]]
    stop_bps: float
    soft_hold_minutes: int
    hard_hold_minutes: int
    maximum_entry_delay_seconds: int
    modeled_round_trip_friction_bps: float
    notional_usd_by_symbol: Mapping[str, float]

    def __post_init__(self) -> None:
        """Reject incomplete or success-shaped counterfactual contracts."""
        if not self.source_strategy_id.strip() or not self.source_run_id.strip():
            raise ValueError("breakout strategy and source run must be non-empty")
        if self.cutoff_time_ms < 0:
            raise ValueError("breakout cutoff time must be nonnegative")
        if not self.symbols or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("breakout symbols must be unique and non-empty")
        if any(symbol != symbol.upper() or not symbol for symbol in self.symbols):
            raise ValueError("breakout symbols must be uppercase and non-empty")
        if not set(self.source_execution_symbols).issubset(self.symbols):
            raise ValueError("source execution symbols must be candidate symbols")
        _validate_competing_providers(self)
        if not math.isfinite(self.stop_bps) or self.stop_bps <= 0.0:
            raise ValueError("breakout stop bps must be positive and finite")
        if (
            self.soft_hold_minutes < 1
            or self.hard_hold_minutes <= self.soft_hold_minutes
        ):
            raise ValueError("hard hold must be later than the positive soft hold")
        if self.maximum_entry_delay_seconds < 1:
            raise ValueError("maximum entry delay must be positive")
        if (
            not math.isfinite(self.modeled_round_trip_friction_bps)
            or self.modeled_round_trip_friction_bps < 0.0
        ):
            raise ValueError("modeled friction must be nonnegative and finite")
        if set(self.notional_usd_by_symbol) != set(self.symbols):
            raise ValueError("breakout notionals must cover every symbol exactly")
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in self.notional_usd_by_symbol.values()
        ):
            raise ValueError("breakout notionals must be positive and finite")


def breakout_report_contract(spec: BreakoutPolicyForwardSpec) -> dict[str, object]:
    """Disclose the policy proxy and its lack of execution authority."""
    return {
        "counterfactual_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "source_strategy_id": spec.source_strategy_id,
        "source_run_id": spec.source_run_id,
        "source_execution_symbols": list(spec.source_execution_symbols),
        "stop_bps": spec.stop_bps,
        "soft_hold_minutes": spec.soft_hold_minutes,
        "timer_anchor": "decision_time_proxy",
        "maximum_hold_policy": "extend_while_regime_supported",
        "hard_hold_minutes": spec.hard_hold_minutes,
        "opposite_intent_policy": "close_without_same_cycle_reversal",
        "counterfactual_fill_claimed_as_actual": False,
        "actual_execution_evidence": "cohort_snapshot_recent_fills_when_matched",
        "cross_provider_router_contention_modeled": False,
    }


def breakout_report_limitations() -> list[str]:
    """Return limitations that prevent live-PnL interpretation."""
    return [
        "reference prices are decision-time proxies, not private IOC fills",
        "timer deadlines use decision time because counterfactual fill time is unavailable",
        "one-minute OHLC cannot resolve queueing, sub-minute stop order, or gap slippage",
        "modeled counterfactual friction excludes funding; matched actual fills retain recorded funding",
        "cross-provider executable contention is disclosed but not replayed",
        "small and overlapping signal samples are descriptive rather than independent edge evidence",
    ]


def _validate_competing_providers(spec: BreakoutPolicyForwardSpec) -> None:
    if not set(spec.competing_execution_providers_by_symbol).issubset(spec.symbols):
        raise ValueError("competing provider symbols must be candidate symbols")
    for providers in spec.competing_execution_providers_by_symbol.values():
        if (
            not providers
            or len(set(providers)) != len(providers)
            or any(not value.strip() for value in providers)
        ):
            raise ValueError("competing provider ids must be unique and non-empty")
