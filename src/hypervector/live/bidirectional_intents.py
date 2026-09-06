"""Deterministic multi-asset routing for attributed long and short intents."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Literal

from hypervector.live.perp_venue_identity import parse_perp_venue_identity

Direction = Literal["long", "short"]
RoutingActionName = Literal["enter", "close"]
RegimeAlignmentStance = Literal[
    "directionally_supported",
    "directionally_opposed",
    "mixed_or_transition",
]
PositionInteractionPolicy = Literal["enter_and_close", "flat_entry_only"]
_BOTH_SIDES = frozenset({"long", "short"})
_REGIME_STANCES = frozenset(
    {
        "directionally_supported",
        "directionally_opposed",
        "mixed_or_transition",
    }
)


@dataclass(frozen=True)
class StrategyCapability:
    """Declared direction capability and routing priority for one provider."""

    strategy_id: str
    symbol: str
    sides: frozenset[str]
    priority: int
    position_policy: PositionInteractionPolicy = "enter_and_close"

    def __post_init__(self) -> None:
        """Reject undeclared directions or malformed provider identity."""
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        _validate_symbol(self.symbol)
        if not self.sides or not self.sides.issubset(_BOTH_SIDES):
            raise ValueError("strategy sides must contain long and/or short")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("strategy priority must be an integer")
        if self.position_policy not in {"enter_and_close", "flat_entry_only"}:
            raise ValueError("strategy position policy is unsupported")


@dataclass(frozen=True)
class StrategyIntent:
    """One causal, strategy-attributed request to hold directional exposure."""

    strategy_id: str
    symbol: str
    side: str
    decision_time_ms: int
    reference_price: float
    reason: str
    stop_anchor: float | None = None
    target_anchor: float | None = None
    regime_alignment_score: float | None = None
    regime_alignment_stance: RegimeAlignmentStance | None = None
    regime_decision_time_ms: int | None = None
    regime_alignment_basis: str | None = None

    def __post_init__(self) -> None:
        """Reject malformed or ambiguous execution intent."""
        if not self.strategy_id.strip() or not self.reason.strip():
            raise ValueError("intent strategy_id and reason must be non-empty")
        _validate_symbol(self.symbol)
        if self.side not in _BOTH_SIDES:
            raise ValueError("intent side must be long or short")
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
        ):
            raise ValueError("intent decision_time_ms must be nonnegative")
        if not math.isfinite(self.reference_price) or self.reference_price <= 0.0:
            raise ValueError("intent reference_price must be positive and finite")
        if self.stop_anchor is not None and (
            not math.isfinite(self.stop_anchor) or self.stop_anchor <= 0.0
        ):
            raise ValueError("intent stop_anchor must be positive and finite")
        if self.target_anchor is not None and (
            not math.isfinite(self.target_anchor) or self.target_anchor <= 0.0
        ):
            raise ValueError("intent target_anchor must be positive and finite")
        _validate_regime_preference(self)


@dataclass(frozen=True)
class PositionState:
    """Venue-authoritative one-way position direction for one symbol."""

    symbol: str
    side: str | None

    def __post_init__(self) -> None:
        """Reject a malformed venue projection."""
        _validate_symbol(self.symbol)
        if self.side is not None and self.side not in _BOTH_SIDES:
            raise ValueError("position side must be long, short, or None")


@dataclass(frozen=True)
class RoutingAction:
    """One selected entry or close action with originating strategy identity."""

    action: RoutingActionName
    strategy_id: str
    symbol: str
    side: str
    decision_time_ms: int
    reference_price: float
    stop_anchor: float | None = None
    target_anchor: float | None = None
    regime_alignment_score: float | None = None
    regime_alignment_stance: RegimeAlignmentStance | None = None
    regime_decision_time_ms: int | None = None
    regime_alignment_basis: str | None = None
    exit_reason: str | None = None
    submission_observed_at_ms: int | None = None
    submission_age_ms: int | None = None
    submission_limit_ms: int | None = None


@dataclass(frozen=True)
class WithheldIntent:
    """One unexecuted intent and its explicit portfolio reason."""

    intent: StrategyIntent
    reason: str
    submission_observed_at_ms: int | None = None
    submission_age_ms: int | None = None
    submission_limit_ms: int | None = None


@dataclass(frozen=True)
class IntentRoutingReport:
    """All selected actions and withheld alternatives for one cycle."""

    actions: tuple[RoutingAction, ...]
    withheld: tuple[WithheldIntent, ...]


class BidirectionalIntentRouter:
    """Resolve attributed intents without performance or confidence gates."""

    def __init__(
        self,
        capabilities: tuple[StrategyCapability, ...],
        *,
        maximum_positions: int,
    ) -> None:
        if not capabilities:
            raise ValueError("intent router requires strategy capabilities")
        if (
            isinstance(maximum_positions, bool)
            or not isinstance(maximum_positions, int)
            or maximum_positions < 1
        ):
            raise ValueError("maximum_positions must be a positive integer")
        self._priorities = _capability_priorities(capabilities)
        self._position_policies = _capability_position_policies(capabilities)
        self._sides = {
            (capability.strategy_id, capability.symbol): capability.sides
            for capability in capabilities
        }
        self._symbols = tuple(
            dict.fromkeys(capability.symbol for capability in capabilities)
        )
        self._maximum_positions = maximum_positions

    @property
    def symbols(self) -> tuple[str, ...]:
        """Return enabled symbols in declared order."""
        return self._symbols

    @property
    def maximum_positions(self) -> int:
        """Return the explicit shared-account position capacity."""
        return self._maximum_positions

    def route(
        self,
        intents: tuple[StrategyIntent, ...],
        *,
        positions: dict[str, PositionState],
    ) -> IntentRoutingReport:
        """Select at most one deterministic action per symbol for this cycle."""
        _validate_positions(positions, self._symbols)
        selected, withheld = self._select_intents(intents, positions)
        open_count = sum(position.side is not None for position in positions.values())
        actions: list[RoutingAction] = []
        for intent in selected:
            action, reason = _position_action(
                intent,
                positions[intent.symbol],
                self._position_policies[(intent.strategy_id, intent.symbol)],
            )
            if reason is not None:
                withheld.append(WithheldIntent(intent, reason))
                continue
            if action == "enter" and open_count >= self._maximum_positions:
                withheld.append(WithheldIntent(intent, "portfolio_position_capacity"))
                continue
            actions.append(_routing_action(action, intent))
            if action == "enter":
                open_count += 1
        return IntentRoutingReport(tuple(actions), tuple(withheld))

    def _select_intents(
        self,
        intents: tuple[StrategyIntent, ...],
        positions: dict[str, PositionState],
    ) -> tuple[list[StrategyIntent], list[WithheldIntent]]:
        groups: dict[str, list[StrategyIntent]] = defaultdict(list)
        order: list[str] = []
        for intent in intents:
            self._require_capability(intent)
            if intent.symbol not in groups:
                order.append(intent.symbol)
            groups[intent.symbol].append(intent)
        selected: list[StrategyIntent] = []
        withheld: list[WithheldIntent] = []
        for symbol in order:
            choice, alternatives = self._select_symbol(
                groups[symbol], positions[symbol].side
            )
            selected.append(choice)
            withheld.extend(alternatives)
        return selected, withheld

    def _select_symbol(
        self,
        intents: list[StrategyIntent],
        open_side: str | None,
    ) -> tuple[StrategyIntent, list[WithheldIntent]]:
        ranked = sorted(
            intents,
            key=lambda intent: (
                _routing_regime_score(intent),
                self._priorities[(intent.strategy_id, intent.symbol)],
                intent.decision_time_ms,
            ),
            reverse=True,
        )
        exits = [
            intent
            for intent in ranked
            if open_side is not None
            and intent.side != open_side
            and self._position_policies[(intent.strategy_id, intent.symbol)]
            == "enter_and_close"
        ]
        choice = exits[0] if exits else ranked[0]
        exit_precedence = bool(exits) and choice is not ranked[0]
        alternatives = list(ranked)
        alternatives.remove(choice)
        alternatives = [
            WithheldIntent(
                intent,
                _conflict_reason(
                    choice,
                    intent,
                    exit_precedence=exit_precedence,
                    open_side=open_side,
                ),
            )
            for intent in alternatives
        ]
        return choice, alternatives

    def _require_capability(self, intent: StrategyIntent) -> None:
        key = (intent.strategy_id, intent.symbol)
        if key not in self._priorities:
            raise ValueError(
                f"undeclared strategy capability: {intent.strategy_id}/{intent.symbol}"
            )
        if intent.side not in self._sides[key]:
            raise ValueError(
                "undeclared strategy direction: "
                f"{intent.strategy_id}/{intent.symbol}/{intent.side}"
            )


def _capability_priorities(
    capabilities: tuple[StrategyCapability, ...],
) -> dict[tuple[str, str], int]:
    priorities: dict[tuple[str, str], int] = {}
    for capability in capabilities:
        key = (capability.strategy_id, capability.symbol)
        if key in priorities:
            raise ValueError(f"duplicate strategy capability: {key}")
        priorities[key] = capability.priority
    return priorities


def _capability_position_policies(
    capabilities: tuple[StrategyCapability, ...],
) -> dict[tuple[str, str], PositionInteractionPolicy]:
    return {
        (capability.strategy_id, capability.symbol): capability.position_policy
        for capability in capabilities
    }


def _validate_positions(
    positions: dict[str, PositionState],
    symbols: tuple[str, ...],
) -> None:
    if set(positions) != set(symbols):
        raise ValueError("position snapshot must cover every enabled symbol exactly")
    for symbol, position in positions.items():
        if position.symbol != symbol:
            raise ValueError("position snapshot key differs from its symbol")


def _position_action(
    intent: StrategyIntent,
    position: PositionState,
    policy: PositionInteractionPolicy,
) -> tuple[RoutingActionName, str | None]:
    if position.side is None:
        return "enter", None
    if policy == "flat_entry_only":
        return "enter", "provider_flat_entry_only"
    if position.side == intent.side:
        return "enter", "same_direction_position_open"
    return "close", None


def _routing_action(
    action: RoutingActionName,
    intent: StrategyIntent,
) -> RoutingAction:
    return RoutingAction(
        action=action,
        strategy_id=intent.strategy_id,
        symbol=intent.symbol,
        side=intent.side,
        decision_time_ms=intent.decision_time_ms,
        reference_price=intent.reference_price,
        stop_anchor=intent.stop_anchor,
        target_anchor=intent.target_anchor,
        regime_alignment_score=intent.regime_alignment_score,
        regime_alignment_stance=intent.regime_alignment_stance,
        regime_decision_time_ms=intent.regime_decision_time_ms,
        regime_alignment_basis=intent.regime_alignment_basis,
    )


def _routing_regime_score(intent: StrategyIntent) -> float:
    return intent.regime_alignment_score or 0.0


def _conflict_reason(
    choice: StrategyIntent,
    alternative: StrategyIntent,
    *,
    exit_precedence: bool = False,
    open_side: str | None = None,
) -> str:
    if exit_precedence and alternative.side == open_side:
        return "opposite_position_exit_precedence"
    if _routing_regime_score(choice) > _routing_regime_score(alternative):
        return "lower_regime_alignment"
    return "lower_provider_priority"


def _validate_regime_preference(intent: StrategyIntent) -> None:
    values = (
        intent.regime_alignment_score,
        intent.regime_alignment_stance,
        intent.regime_decision_time_ms,
        intent.regime_alignment_basis,
    )
    if all(value is None for value in values):
        return
    if any(value is None for value in values):
        raise ValueError("intent regime preference must be complete when reported")
    score = intent.regime_alignment_score
    decision_time = intent.regime_decision_time_ms
    basis = intent.regime_alignment_basis
    if score is None or not math.isfinite(score) or not -1.0 <= score <= 1.0:
        raise ValueError("intent regime alignment score must be within [-1, 1]")
    if intent.regime_alignment_stance not in _REGIME_STANCES:
        raise ValueError("intent regime alignment stance is unsupported")
    if (
        isinstance(decision_time, bool)
        or not isinstance(decision_time, int)
        or decision_time < 0
    ):
        raise ValueError("intent regime decision time must be nonnegative")
    if basis is None or not basis.strip():
        raise ValueError("intent regime alignment basis must be non-empty")


def _validate_symbol(value: str) -> None:
    try:
        parse_perp_venue_identity(value)
    except ValueError as exc:
        raise ValueError(f"symbol must be an exact venue identity: {exc}") from exc
