"""Bind HIP-3 shadow replays to one exact live provider exit contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

from hypervector.cohort_profit_lock_policy import ProfitLockPolicy
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
    LifecycleSide,
)

LIVE_BOUND_HIP3_SYMBOLS = frozenset({"xyz:SP500", "xyz:SPCX"})


def bind_live_execution_contract(
    base: Hip3ShadowLifecycleConfig,
    source: Path,
) -> Hip3ShadowLifecycleConfig:
    """Return a replay config matching one exact executable live route."""
    live = load_multi_asset_live_config(source, mode="observe")
    provider = _exact_provider(live, base)
    contract = _symmetric_contract(provider, base.symbol)
    _require_supported_contract(contract)
    entry_sides = cast(frozenset[LifecycleSide], provider.executable_sides(base.symbol))
    return replace(
        base,
        entry_sides=entry_sides,
        maximum_hold_minutes=contract.maximum_hold_seconds // 60,
        fixed_stop_bps=contract.stop_bps,
        signal_exit_enabled=contract.provider_recipe_exit_policy == "honor",
        opposite_entry_exit_enabled=(
            provider.position_policy == "enter_and_close" and len(entry_sides) == 2
        ),
        profit_lock_policy=_profit_lock(live, base.symbol, contract),
        execution_profile_id=live.profile_id,
        execution_profile_fingerprint=live.profile_fingerprint,
    )


def _exact_provider(
    live: MultiAssetLiveConfig,
    base: Hip3ShadowLifecycleConfig,
) -> StrategyProviderConfig:
    routes = tuple(
        provider
        for provider in live.providers
        if base.symbol in provider.execution_symbols
    )
    matches = tuple(
        provider for provider in routes if provider.strategy_id == base.provider_id
    )
    if len(routes) != 1 or len(matches) != 1:
        raise ValueError("HIP-3 replay requires one exact executable live provider")
    provider = matches[0]
    executable = provider.executable_sides(base.symbol)
    if provider.timeframe != "15m" or not executable:
        raise ValueError(
            "HIP-3 replay live provider scope is not executable on exact 15m"
        )
    return provider


def _symmetric_contract(
    provider: StrategyProviderConfig,
    symbol: str,
) -> ProviderExecutionContract:
    long = provider.execution_for(symbol, "long")
    short = provider.execution_for(symbol, "short")
    if long != short:
        raise ValueError("HIP-3 replay cannot alias asymmetric live exit contracts")
    return long


def _require_supported_contract(contract: ProviderExecutionContract) -> None:
    supported = (
        contract.entry_liquidity == "taker_ioc"
        and contract.stop_policy == "fixed_bps"
        and contract.stop_bps is not None
        and contract.target_policy == "none"
        and contract.maximum_hold_policy == "fixed"
        and contract.hard_maximum_hold_seconds is None
        and contract.maximum_hold_seconds % 60 == 0
        and not contract.safety_stop_overlay
    )
    if not supported:
        raise ValueError("HIP-3 replay does not support the configured live exit shape")


def _profit_lock(
    live: MultiAssetLiveConfig,
    symbol: str,
    contract: ProviderExecutionContract,
) -> ProfitLockPolicy | None:
    if contract.profit_lock_policy == "none":
        return None
    values = (
        contract.profit_lock_activation_bps,
        contract.profit_lock_floor_bps,
        contract.profit_lock_giveback_bps,
    )
    if any(value is None for value in values):
        raise ValueError("HIP-3 live profit-lock contract is incomplete")
    version = live.profile_id.rsplit("_", 1)[-1]
    token = symbol.removeprefix("xyz:").lower()
    activation, floor, giveback = (float(value) for value in values)
    policy_id = f"{version}_hip3_{token}_{activation:g}_{floor:g}_{giveback:g}"
    return ProfitLockPolicy(policy_id, activation, floor, giveback)
