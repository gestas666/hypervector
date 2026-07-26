"""Fixed, observed Hypervelocity baseline contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from hypervector.regime.models import BreakoutDirection, PrimaryRegime

if TYPE_CHECKING:
    from hypervector.regime.classifier import RegimeClassifierConfig

EntryDirection = Literal["long", "short"]

_MARGIN_FRACTION = 0.70
_LEVERAGE = 40.0
_TARGET_MARGIN_PCT = 8.0
_OPEN_POSITION_RANGE_POLICY = "hold_until_target"
_ENTRY_TTL_SECONDS = 300.0
_EXPIRED_ENTRY_REARM_POLICY = "regime_reset"
_SAME_DIRECTION_REENTRY_POLICY = "regime_reset"
_STRATEGY_NAMES = frozenset(
    {
        "hypervelocity_1m_scalper",
        "hypervelocity_1m_scalper_long",
        "hypervelocity_1m_scalper_short",
    }
)


def is_hypervelocity_strategy(strategy_name: str) -> bool:
    """Return whether a registry name uses the fixed Hypervelocity contract."""
    return str(strategy_name) in _STRATEGY_NAMES


def faithful_regime_config() -> RegimeClassifierConfig:
    """Return the training Pareto candidate with no RANGE/no-entry logged states."""
    from hypervector.regime.classifier import RegimeClassifierConfig

    return RegimeClassifierConfig(
        ema_fast=5,
        ema_slow=13,
        warmup_bars=60,
        structure_lookback=120,
        trend_strength_percentile=70.0,
        range_strength_percentile=40.0,
        minimum_trend_gap_bps=0.5,
        choppiness_range_threshold=75.0,
        coiling_width_bps=1.0,
        breakout_lookback=90,
        breakout_clearance_bps=8.0,
        breakout_volume_multiple=2.5,
    )


@dataclass(frozen=True)
class HypervelocityAllocation:
    """Margin and notional allocated for one candidate trade."""

    margin: float
    notional: float


@dataclass(frozen=True)
class HypervelocityContract:
    """Immutable facts of the faithful BTC Hypervelocity baseline."""

    margin_fraction: float = _MARGIN_FRACTION
    leverage: float = _LEVERAGE
    target_margin_pct: float = _TARGET_MARGIN_PCT
    order_type: str = "limit"
    time_in_force: str = "post_only"
    open_position_range_policy: str = _OPEN_POSITION_RANGE_POLICY
    entry_ttl_seconds: float = _ENTRY_TTL_SECONDS
    expired_entry_rearm_policy: str = _EXPIRED_ENTRY_REARM_POLICY
    same_direction_reentry_policy: str = _SAME_DIRECTION_REENTRY_POLICY

    def __post_init__(self) -> None:
        if self.margin_fraction != _MARGIN_FRACTION:
            raise ValueError("margin_fraction must be 0.70 for the faithful baseline")
        if self.leverage != _LEVERAGE:
            raise ValueError("leverage must be 40.0 for the faithful baseline")
        if self.target_margin_pct != _TARGET_MARGIN_PCT:
            raise ValueError("target_margin_pct must be 8.0 for the faithful baseline")
        if self.order_type != "limit" or self.time_in_force != "post_only":
            raise ValueError("faithful baseline execution must be limit post_only")
        if self.open_position_range_policy != _OPEN_POSITION_RANGE_POLICY:
            raise ValueError("open positions must hold through range until target")
        if self.entry_ttl_seconds != _ENTRY_TTL_SECONDS:
            raise ValueError("entry_ttl_seconds must be 300.0")
        if self.expired_entry_rearm_policy != _EXPIRED_ENTRY_REARM_POLICY:
            raise ValueError("expired entries must re-arm after a regime reset")
        if self.same_direction_reentry_policy != _SAME_DIRECTION_REENTRY_POLICY:
            raise ValueError("completed trades must re-arm after a regime reset")

    @property
    def target_price_fraction(self) -> float:
        """Return the unlevered price move required for the margin target."""
        return self.target_margin_pct / self.leverage / 100.0

    @property
    def notional_fraction(self) -> float:
        """Return notional divided by equity for the fixed allocation."""
        return self.margin_fraction * self.leverage

    def allocate(self, equity: float) -> HypervelocityAllocation:
        """Allocate 70% of positive equity as margin at 40x leverage."""
        equity_value = float(equity)
        if equity_value <= 0.0:
            raise ValueError(f"equity must be positive, got {equity!r}")
        margin = equity_value * self.margin_fraction
        return HypervelocityAllocation(
            margin=margin,
            notional=margin * self.leverage,
        )


def entry_direction_for(
    primary: PrimaryRegime,
    breakout: BreakoutDirection | None = None,
) -> EntryDirection | None:
    """Map an authoritative regime event to an allowed entry direction."""
    if primary is PrimaryRegime.TREND_UP:
        return "long"
    if primary is PrimaryRegime.TREND_DOWN:
        return "short"
    if primary is PrimaryRegime.BREAKOUT:
        if breakout is BreakoutDirection.UPWARD:
            return "long"
        if breakout is BreakoutDirection.DOWNWARD:
            return "short"
    return None
