"""Pure routing-action serialization helpers for the live cohort runner."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live import cohort_execution_contract_selection as contract_selection
from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    ProviderExecutionContract,
)
from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.multi_asset_live_protocols import MultiAssetEngineProtocol
from hypervector.live.multi_asset_live_runner_support import entry_provider_strategy_id


STRUCTURAL_ANCHOR_REFUSAL = "structural_anchor_not_adverse"


def routing_decision_payload(
    action: RoutingAction,
    execution_plan: BoundExecutionPlan | None,
    entry_sizing: CohortEntrySizing | None,
    sizing_source: str,
    entry_refusal: str | None = None,
) -> dict[str, object]:
    """Serialize one routed action with its immutable execution contract."""
    return {
        **({"entry_refusal": entry_refusal} if entry_refusal is not None else {}),
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


def execute_routing_action(
    action: RoutingAction,
    *,
    engine: MultiAssetEngineProtocol,
    contracts: Mapping[
        contract_selection.ExecutionContractKey, ProviderExecutionContract
    ],
    directional_sizing: Mapping[tuple[str, str, str], CohortEntrySizing],
    fallback_sizing: Mapping[tuple[str, str], CohortEntrySizing],
    entry_deadline: EntrySubmissionDeadline | None = None,
) -> None:
    """Bind, journal, and execute one already-admitted routing action."""
    plan = contract_selection.bind_execution_plan(contracts, action)
    provider = entry_provider_strategy_id(action.strategy_id)
    sizing, source = select_entry_sizing(
        provider, action.symbol, action.side, directional_sizing, fallback_sizing
    )
    refusal = (
        STRUCTURAL_ANCHOR_REFUSAL
        if action.action == "enter"
        and plan is not None
        and plan.structural_anchor_overrun(action.reference_price, action.side)
        else None
    )
    engine.record_strategy_decision(
        routing_decision_payload(action, plan, sizing, source, entry_refusal=refusal)
    )
    if refusal is not None:
        return
    if action.action == "enter":
        engine.enter(
            side=action.side,
            mark_price=action.reference_price,
            decision_time_ms=action.decision_time_ms,
            entry_sizing=sizing,
            **(
                {"entry_deadline": entry_deadline} if entry_deadline is not None else {}
            ),
        )
        return
    engine.exit(mark_price=action.reference_price, reason=routing_exit_reason(action))
