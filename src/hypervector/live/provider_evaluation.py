"""Neutral provider output types: one poll's intents and per-bar evaluations.

Every live signal provider returns an ``IntentBatch``: the entry intents it
emits, the latest completed decision boundary it processed, and one
``ProviderEvaluation`` per evaluated completed bar (readiness, exits and
non-action reasons for telemetry). Nothing here names a strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.provider_readiness import SignalReadiness


@dataclass(frozen=True)
class IntentBatch:
    """All entry intents plus the latest processed decision boundary."""

    intents: tuple[StrategyIntent, ...]
    latest_decision_time_ms: int
    evaluations: tuple[ProviderEvaluation, ...] = ()


@dataclass(frozen=True)
class ProviderEvaluation:
    """One backend-authored completed-bar setup and firing-readiness record."""

    strategy_id: str
    symbol: str
    decision_time_ms: int
    reference_price: float
    decision_action: str
    eligible: bool
    reason: str
    side: str | None
    readiness: SignalReadiness
    score: int | None = None
    minimum_score: int | None = None
    trigger: str | None = None
    primary_regime: str | None = None
    state_1m: str | None = None
    state_5m: str | None = None
    context_15m: str | None = None
    confidence: float | None = None
    exit_sides: frozenset[str] = frozenset()
    exit_reason: str | None = None
    backend_non_action_reason: str | None = None
    target_anchor: float | None = None

    def __post_init__(self) -> None:
        """Reject malformed provider identity, direction, and market evidence."""
        if not self.strategy_id.strip() or not self.symbol.strip():
            raise ValueError("provider evaluation identity must be non-empty")
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
        ):
            raise ValueError("decision_time_ms must be a nonnegative integer")
        if not math.isfinite(self.reference_price) or self.reference_price <= 0.0:
            raise ValueError("reference_price must be positive and finite")
        if not isinstance(self.eligible, bool):
            raise ValueError("eligible must be boolean")
        if not self.decision_action.strip() or not self.reason.strip():
            raise ValueError("provider action and reason must be non-empty")
        if self.side not in {None, "long", "short"}:
            raise ValueError("provider side must be long, short, or None")
        if self.eligible and self.side is None:
            raise ValueError("eligible provider evaluations require a side")
        if not self.exit_sides.issubset({"long", "short"}):
            raise ValueError("provider exit sides must contain only long and/or short")
        if bool(self.exit_sides) != bool(self.exit_reason and self.exit_reason.strip()):
            raise ValueError("provider exit sides and reason must be reported together")
        if self.backend_non_action_reason is not None and not (
            self.backend_non_action_reason.strip()
        ):
            raise ValueError(
                "backend non-action reason must be non-empty when reported"
            )
        if self.target_anchor is not None and (
            not math.isfinite(self.target_anchor) or self.target_anchor <= 0.0
        ):
            raise ValueError("provider target_anchor must be positive and finite")
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("provider confidence must be within [0, 1]")

    def as_payload(self) -> dict[str, object]:
        """Return exact signal facts and diagnostic readiness for the TUI."""
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "decision_time_ms": self.decision_time_ms,
            "reference_price": self.reference_price,
            "decision_action": self.decision_action,
            "eligible": self.eligible,
            "reason": self.reason,
            "side": self.side,
            "score": self.score,
            "minimum_score": self.minimum_score,
            "trigger": self.trigger,
            "primary_regime": self.primary_regime,
            "state_1m": self.state_1m,
            "state_5m": self.state_5m,
            "context_15m": self.context_15m,
            "confidence": self.confidence,
            "exit_sides": sorted(self.exit_sides),
            "exit_reason": self.exit_reason,
            "backend_non_action_reason": self.backend_non_action_reason,
            "target_anchor": self.target_anchor,
            "readiness": self.readiness.as_payload(),
        }
