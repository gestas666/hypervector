"""Report-only growth route classification and after-friction sizing."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

GrowthTier = Literal["base", "strong", "exceptional"]

_TIER_RISK = {"base": 0.01, "strong": 0.015, "exceptional": 0.02}
_TARGET_MARGIN_FRACTION = 0.125
_STRONG_MINIMUM_CLOSES = 30
_EXCEPTIONAL_MINIMUM_CLOSES = 100


@dataclass(frozen=True)
class GrowthRouteEvidence:
    """Minimum causal evidence needed to recommend one route-risk ceiling."""

    route_id: str
    technical_resolved: bool
    oos_evaluated: bool
    known_negative: bool
    exact_forward_closes: int
    stress_profit_factor: float | None
    stress_ex_largest_net_usd: float | None
    positive_fold_fraction: float | None
    sizing_monotonicity_resolved: bool

    def __post_init__(self) -> None:
        """Reject malformed counts, metrics, and evidence identities."""
        if not isinstance(self.route_id, str) or not self.route_id.strip():
            raise ValueError("growth route identity must be non-empty")
        for label, value in _boolean_evidence(self):
            if not isinstance(value, bool):
                raise ValueError(f"{label} must be boolean")
        if isinstance(self.exact_forward_closes, bool) or not isinstance(
            self.exact_forward_closes, int
        ):
            raise ValueError("growth route closes must be an integer")
        if self.exact_forward_closes < 0:
            raise ValueError("growth route closes must be nonnegative")
        _optional_finite(self.stress_profit_factor, "stress profit factor")
        _optional_finite(self.stress_ex_largest_net_usd, "stress ex-largest net")
        if self.positive_fold_fraction is not None:
            if isinstance(self.positive_fold_fraction, bool):
                raise ValueError("positive fold fraction must be numeric")
            if not (0.0 <= self.positive_fold_fraction <= 1.0):
                raise ValueError("positive fold fraction must be within [0, 1]")
        if self.oos_evaluated and self.stress_profit_factor is None:
            raise ValueError("evaluated OOS evidence requires stress economics")


@dataclass(frozen=True)
class GrowthRouteDecision:
    """Report-only route disposition with no execution authority."""

    route_id: str
    disposition: str
    maximum_tier: GrowthTier | None
    risk_fraction: float | None
    reason: str
    execution_authority: str = "none"


@dataclass(frozen=True)
class GrowthTierScenario:
    """One tier's notional, leverage, margin, and after-friction stop loss."""

    tier: GrowthTier
    risk_fraction: float
    notional_usd: float
    leverage: float
    margin_usd: float
    margin_fraction: float
    planned_stop_loss_after_friction_usd: float
    leverage_cap_binding: bool


def classify_growth_route(evidence: GrowthRouteEvidence) -> GrowthRouteDecision:
    """Classify evidence without granting live or sizing authority."""
    if evidence.known_negative:
        return _decision(evidence, "exclude_known_negative", None)
    if not evidence.technical_resolved:
        return _decision(evidence, "prospective_capture_only", None)
    if _falsified_economics(evidence):
        return _decision(evidence, "exclude_falsified_economics", None)
    if _exceptional_ready(evidence):
        return _decision(evidence, "exceptional_evidence", "exceptional")
    if _strong_ready(evidence):
        return _decision(evidence, "strong_evidence", "strong")
    return _decision(evidence, "base_live_research", "base")


def build_growth_tier_scenarios(
    *,
    equity_usd: float,
    stop_bps: float,
    fee_bps_per_side: float,
    slippage_bps_per_side: float,
    venue_max_leverage: float,
) -> tuple[GrowthTierScenario, ...]:
    """Size tiers from after-friction stop risk before choosing leverage."""
    equity = _positive(equity_usd, "equity")
    stop = _positive(stop_bps, "stop bps")
    fee = _nonnegative(fee_bps_per_side, "fee bps")
    slippage = _nonnegative(slippage_bps_per_side, "slippage bps")
    venue_max = _positive(venue_max_leverage, "venue maximum leverage")
    loss_bps = stop + 2.0 * (fee + slippage)
    return tuple(
        _tier_scenario(tier, equity, loss_bps, venue_max)
        for tier in ("base", "strong", "exceptional")
    )


def _tier_scenario(
    tier: GrowthTier,
    equity: float,
    loss_bps: float,
    venue_max: float,
) -> GrowthTierScenario:
    risk_fraction = _TIER_RISK[tier]
    risk_usd = equity * risk_fraction
    notional = risk_usd / (loss_bps / 10_000.0)
    required = max(1.0, float(math.ceil(notional / equity / _TARGET_MARGIN_FRACTION)))
    leverage = min(required, venue_max)
    margin = notional / leverage
    return GrowthTierScenario(
        tier,
        risk_fraction,
        notional,
        leverage,
        margin,
        margin / equity,
        notional * loss_bps / 10_000.0,
        required > venue_max,
    )


def _decision(
    evidence: GrowthRouteEvidence,
    disposition: str,
    tier: GrowthTier | None,
) -> GrowthRouteDecision:
    reason = {
        "exclude_known_negative": "existing after-cost evidence rejects the route",
        "prospective_capture_only": "venue or signal path remains unresolved",
        "exclude_falsified_economics": "OOS stress economics are nonpositive",
        "exceptional_evidence": "broad OOS evidence and sizing monotonicity resolved",
        "strong_evidence": "repeatable OOS after-cost evidence survived concentration",
        "base_live_research": "technically executable; larger tiers remain unproven",
    }[disposition]
    return GrowthRouteDecision(
        evidence.route_id,
        disposition,
        tier,
        _TIER_RISK[tier] if tier is not None else None,
        reason,
    )


def _falsified_economics(evidence: GrowthRouteEvidence) -> bool:
    if not evidence.oos_evaluated:
        return False
    profit_factor = evidence.stress_profit_factor
    ex_largest = evidence.stress_ex_largest_net_usd
    return (
        profit_factor is None
        or profit_factor <= 1.0
        or ex_largest is None
        or ex_largest <= 0.0
    )


def _strong_ready(evidence: GrowthRouteEvidence) -> bool:
    return (
        evidence.oos_evaluated
        and evidence.exact_forward_closes >= _STRONG_MINIMUM_CLOSES
        and _at_least(evidence.stress_profit_factor, 1.2)
        and _positive_optional(evidence.stress_ex_largest_net_usd)
        and _at_least(evidence.positive_fold_fraction, 0.6)
    )


def _exceptional_ready(evidence: GrowthRouteEvidence) -> bool:
    return (
        evidence.oos_evaluated
        and evidence.exact_forward_closes >= _EXCEPTIONAL_MINIMUM_CLOSES
        and _at_least(evidence.stress_profit_factor, 1.4)
        and _positive_optional(evidence.stress_ex_largest_net_usd)
        and _at_least(evidence.positive_fold_fraction, 0.8)
        and evidence.sizing_monotonicity_resolved
    )


def _at_least(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _positive_optional(value: float | None) -> bool:
    return value is not None and value > 0.0


def _optional_finite(value: float | None, label: str) -> None:
    if value is not None and (isinstance(value, bool) or not math.isfinite(value)):
        raise ValueError(f"{label} must be finite when provided")


def _boolean_evidence(
    evidence: GrowthRouteEvidence,
) -> tuple[tuple[str, object], ...]:
    return (
        ("technical_resolved", evidence.technical_resolved),
        ("oos_evaluated", evidence.oos_evaluated),
        ("known_negative", evidence.known_negative),
        ("sizing_monotonicity_resolved", evidence.sizing_monotonicity_resolved),
    )


def _positive(value: float, label: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return float(value)


def _nonnegative(value: float, label: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be nonnegative and finite")
    return float(value)
