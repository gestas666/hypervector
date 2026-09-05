"""Canonical non-secret identity payloads for multi-asset profiles."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import (
        AssetLiveConfig,
        StrategyProviderConfig,
    )


def asset_profile_values(config: AssetLiveConfig) -> dict[str, object]:
    """Return stable asset identity without runtime authority fields."""
    values = asdict(config)
    for key in ("mode", "enabled", "accepts_live_risk"):
        values.pop(key)
    if config.entry_slippage_cap_fraction is None:
        values.pop("entry_slippage_cap_fraction")
    return values


def provider_profile_values(config: StrategyProviderConfig) -> dict[str, object]:
    """Return stable provider identity while preserving legacy defaults."""
    values = asdict(config)
    for field in (
        "execution_side_overrides",
        "entry_context_overrides",
        "stop_bps_overrides",
        "sizing_overrides",
        "directional_sizing_overrides",
        "profit_lock_overrides",
    ):
        if not getattr(config, field):
            values.pop(field)
    if config.position_policy == "enter_and_close":
        values.pop("position_policy")
    execution = values.get("execution")
    if not isinstance(execution, dict):
        return values
    if config.execution.provider_recipe_exit_policy == "ignore":
        execution.pop("provider_recipe_exit_policy")
    if config.execution.maximum_hold_evidence_maximum_age_seconds is None:
        execution.pop("maximum_hold_evidence_maximum_age_seconds")
    if config.execution.profit_lock_policy == "none":
        for key in (
            "profit_lock_policy",
            "profit_lock_activation_bps",
            "profit_lock_floor_bps",
            "profit_lock_giveback_bps",
        ):
            execution.pop(key)
    return values
