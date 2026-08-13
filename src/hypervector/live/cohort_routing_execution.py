"""Pure routing-action serialization helpers for the live cohort runner."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import BoundExecutionPlan


def routing_decision_payload(
    action: RoutingAction,
    execution_plan: BoundExecutionPlan | None,
    entry_sizing: CohortEntrySizing | None,
    sizing_source: str,
) -> dict[str, object]:
    """Serialize one routed action with its immutable execution contract."""
    return {
        "strategy_id": action.strategy_id,
        "symbol": action.symbol,
        "side": action.side,
        "decision_time_ms": action.decision_time_ms,
        "reference_price": action.reference_price,
        "routing_action": action.action,
        "regime_alignment_score": action.regime_alignment_score,
        "regime_alignment_stance": action.regime_alignment_stance,
        "regime_decision_time_ms": action.regime_decision_time_ms,
        "regime_alignment_basis": action.regime_alignment_basis,
        "exit_reason": action.exit_reason,
        "execution_plan": (
            execution_plan.as_payload() if execution_plan is not None else None
        ),
        "entry_sizing": entry_sizing.as_payload() if entry_sizing is not None else None,
        "entry_sizing_source": sizing_source,
    }


def routing_exit_reason(action: RoutingAction) -> str:
    """Return the explicit normalized close reason for a routing action."""
    if action.exit_reason is not None:
        return action.exit_reason
    if action.strategy_id == "cohort_maximum_hold":
        return "maximum_hold_seconds"
    if action.strategy_id == "operator_override:manual_close":
        return "operator_manual_close"
    return "opposite_strategy_intent"


def select_entry_sizing(
    provider: str,
    symbol: str,
    side: str,
    directional: Mapping[tuple[str, str, str], CohortEntrySizing],
    fallback: Mapping[tuple[str, str], CohortEntrySizing],
) -> tuple[CohortEntrySizing | None, str]:
    """Select a directional sizing override before provider-symbol sizing."""
    selected = directional.get((provider, symbol, side))
    if selected is not None:
        return selected, "provider_direction_override"
    selected = fallback.get((provider, symbol))
    if selected is not None:
        return selected, "provider_symbol_override"
    return None, "asset_default"
