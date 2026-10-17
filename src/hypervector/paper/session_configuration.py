"""Shared paper configuration contracts.

Offline multi-bar walk and incremental ``on_bar`` for the live daemon share
the same alpha path. No Nautilus node, no venue orders. Funding uses the
configured/last hourly rate offline; optional live refresh is opt-in.
"""

from __future__ import annotations

import logging
from typing import Any


from hypervector.nautilus.load_export import StrategyLoadout
from hypervector.paper.maker_execution import (
    PostOnlyLimitFillModel,
)
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    is_hypervelocity_strategy,
)
from hypervector.strategies.hypervelocity_profile import HypervelocityProfile
from hypervector.strategies.source_follow_profile import (
    SourceFollowHypervelocityProfile,
)

logger = logging.getLogger(__name__)
_OHLCV_REQUIRED = ("open", "high", "low", "close", "volume")


def _exits_dict(loadout: StrategyLoadout) -> dict[str, Any]:
    raw = dict(loadout.exits or {})
    if "mode" not in raw or raw.get("mode") is None:
        if loadout.exit_mode is not None:
            raw["mode"] = loadout.exit_mode
    return raw


def _effective_strategy_params(
    loadout: StrategyLoadout,
    *,
    profile: HypervelocityProfile | None = None,
) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return dict(loadout.params or {})
    if profile is not None:
        return {
            "leverage": profile.leverage,
            "target_margin_pct": profile.target_margin_pct,
        }
    contract = HypervelocityContract()
    return {
        "leverage": contract.leverage,
        "target_margin_pct": contract.target_margin_pct,
    }


def _source_follow_metalabel_policy(
    profile: HypervelocityProfile | None,
) -> dict[str, object] | None:
    if not isinstance(profile, SourceFollowHypervelocityProfile):
        return None
    return {
        "observation_type": "annotation_collection",
        "inference_active": False,
        "bundle_id": None,
        "probabilities_emitted": False,
        "may_filter": False,
        "may_scale": False,
        "execution_authority": "none",
    }


def _effective_exits(
    loadout: StrategyLoadout,
    *,
    profile: HypervelocityProfile | None = None,
) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return dict(loadout.exits or {})
    if profile is not None:
        exits: dict[str, Any] = {
            "mode": "strategy_target_only",
            "target_margin_pct": profile.target_margin_pct,
            "target_price_fraction": (
                profile.target_margin_pct / profile.leverage / 100.0
            ),
            "target_basis": "gross_margin_return_before_costs",
            "stop": None,
            "range_policy": profile.open_position_range_policy,
        }
        if isinstance(profile, SourceFollowHypervelocityProfile):
            exits["maximum_hold_seconds"] = profile.maximum_hold_seconds
        return exits
    contract = HypervelocityContract()
    return {
        "mode": "strategy_target_only",
        "target_margin_pct": contract.target_margin_pct,
        "target_price_fraction": contract.target_price_fraction,
        "target_basis": "gross_margin_return_before_costs",
        "stop": None,
        "range_policy": contract.open_position_range_policy,
    }


def _effective_risk(
    loadout: StrategyLoadout,
    *,
    profile: HypervelocityProfile | None = None,
) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return dict(loadout.risk or {})
    if profile is not None:
        return {
            "mode": "fixed_margin_fraction",
            "margin_fraction": profile.margin_fraction,
            "notional_fraction": profile.margin_fraction * profile.leverage,
        }
    contract = HypervelocityContract()
    return {
        "mode": "fixed_margin_fraction",
        "margin_fraction": contract.margin_fraction,
        "notional_fraction": contract.notional_fraction,
    }


def _effective_execution(
    loadout: StrategyLoadout,
    *,
    profile: HypervelocityProfile | None = None,
) -> dict[str, Any]:
    if not is_hypervelocity_strategy(loadout.strategy_name):
        return {"order_type": "market", "time_in_force": "ioc"}
    contract = HypervelocityContract()
    event_model = profile.shadow_execution_model if profile else "legacy_bar_through_v1"
    execution: dict[str, Any] = {
        "order_type": contract.order_type,
        "time_in_force": contract.time_in_force,
        "fill_rule": (
            "public_l2_trade_event_tape"
            if event_model == "nautilus_event_v1"
            else "through_one_tick"
        ),
        "fill_model": (
            event_model if profile is not None else PostOnlyLimitFillModel.fill_model_id
        ),
        "legacy_comparator": "legacy_bar_through_v1",
        "price_tick_mode": "hyperliquid_dynamic",
        "entry_ttl_seconds": (
            profile.entry_ttl_seconds
            if profile is not None
            else contract.entry_ttl_seconds
        ),
        "expired_entry_rearm_policy": (
            profile.expired_entry_rearm_policy
            if profile is not None
            else contract.expired_entry_rearm_policy
        ),
        "same_direction_reentry_policy": (
            profile.same_direction_reentry_policy
            if profile is not None
            else contract.same_direction_reentry_policy
        ),
        "reentry_cooldown_bars": (
            profile.reentry_cooldown_bars if profile is not None else 1
        ),
    }
    if profile is not None:
        execution.update(_profile_execution(profile))
        if isinstance(profile, SourceFollowHypervelocityProfile):
            execution.update(
                maximum_hold_exit="first_fresh_bbo_taker",
                execution_authority="shadow_only",
            )
    return execution


def _portfolio_spec(
    loadout: StrategyLoadout,
    *,
    profile: HypervelocityProfile | None,
    strategy_name: str,
) -> dict[str, object]:
    return {
        "strategy_name": strategy_name,
        "symbol": loadout.symbol,
        "timeframe": loadout.timeframe,
        "strategy_params": {
            "strategy": profile.strategy_id
            if profile is not None
            else loadout.strategy_name,
            **_effective_strategy_params(loadout, profile=profile),
        },
        "position_policy": profile.position_policy() if profile is not None else None,
        "regime_policy": profile.regime_policy() if profile is not None else None,
        "exits": _effective_exits(loadout, profile=profile),
        "risk": _effective_risk(loadout, profile=profile),
        "execution": _effective_execution(loadout, profile=profile),
    }


def _profile_execution(profile: HypervelocityProfile) -> dict[str, object]:
    """Report the declared event timing and liquidation contract."""
    return dict(
        submit_latency_ms=profile.execution_submit_latency_ms,
        cancel_latency_ms=profile.execution_cancel_latency_ms,
        update_latency_ms=profile.execution_update_latency_ms,
        max_event_age_ms=profile.execution_max_event_age_ms,
        restart_queue_policy=profile.restart_queue_policy,
        liquidation_execution_model=profile.liquidation_execution_model,
        partial_liquidation_supported=profile.partial_liquidation_supported,
        partial_liquidation_threshold_usd=(profile.partial_liquidation_threshold_usd),
        partial_liquidation_fraction=profile.partial_liquidation_fraction,
        liquidation_cooldown_ms=profile.liquidation_cooldown_ms,
        backstop_liquidation_supported=(profile.backstop_liquidation_supported),
        backstop_maintenance_fraction=profile.backstop_maintenance_fraction,
        backstop_accounting_model=profile.backstop_accounting_model,
    )
