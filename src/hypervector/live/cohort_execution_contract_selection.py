"""Resolve exact provider-symbol execution contracts."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.multi_asset_live_runner_support import (
    entry_provider_strategy_id,
)

ExecutionContractKey = str | tuple[str, str] | tuple[str, str, str]


def select_execution_contract(
    contracts: Mapping[ExecutionContractKey, ProviderExecutionContract],
    strategy_id: str,
    symbol: str,
    side: str | None = None,
) -> ProviderExecutionContract | None:
    """Prefer direction, then symbol, then provider contract."""
    provider = entry_provider_strategy_id(strategy_id)
    if side is not None:
        directional = contracts.get((provider, symbol, side))
        if directional is not None:
            return directional
    return contracts.get((provider, symbol), contracts.get(provider))


def bind_execution_plan(
    contracts: Mapping[ExecutionContractKey, ProviderExecutionContract],
    action: RoutingAction,
) -> BoundExecutionPlan | None:
    """Bind one exact entry contract; non-entry actions have no plan."""
    if action.action != "enter":
        return None
    contract = select_execution_contract(
        contracts,
        action.strategy_id,
        action.symbol,
        action.side,
    )
    if contract is None:
        return None
    return contract.bind(
        strategy_id=action.strategy_id,
        stop_anchor=action.stop_anchor,
    )
