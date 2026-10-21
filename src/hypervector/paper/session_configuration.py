"""Effective strategy, exit, risk and execution settings of a paper session.

Every value comes from the strategy bundle plus the registered strategy's
declared :class:`~hypervector.strategies.registry.ExecutionProfile`; the
session identity row records them so a ledger states how it was produced.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from hypervector.nautilus.load_export import StrategyLoadout
from hypervector.paper.maker_execution import PostOnlyLimitFillModel
from hypervector.strategies.registry import execution_profile


def _exits_dict(loadout: StrategyLoadout) -> dict[str, Any]:
    raw = dict(loadout.exits or {})
    if "mode" not in raw or raw.get("mode") is None:
        if loadout.exit_mode is not None:
            raw["mode"] = loadout.exit_mode
    return raw


def _effective_strategy_params(loadout: StrategyLoadout) -> dict[str, Any]:
    return dict(loadout.params or {})


def _effective_exits(loadout: StrategyLoadout) -> dict[str, Any]:
    return dict(loadout.exits or {})


def _effective_risk(loadout: StrategyLoadout) -> dict[str, Any]:
    """The bundle's risk band, or the declared fixed margin allocation."""
    execution = execution_profile(loadout.strategy_name)
    if not execution.fixed_sizing:
        return dict(loadout.risk or {})
    return {
        "mode": "fixed_margin_fraction",
        "margin_fraction": execution.fixed_margin_fraction,
        "notional_fraction": execution.fixed_notional_fraction,
        "leverage": execution.leverage,
    }


def _effective_execution(loadout: StrategyLoadout) -> dict[str, Any]:
    """Order types the session simulates (market IOC unless declared post-only)."""
    execution = execution_profile(loadout.strategy_name)
    if not execution.post_only_entries:
        return {"order_type": "market", "time_in_force": "ioc"}
    return {
        "order_type": "limit",
        "time_in_force": "post_only",
        "fill_rule": "through_one_tick",
        "fill_model": PostOnlyLimitFillModel.fill_model_id,
        "entry_ttl_seconds": execution.entry_ttl_seconds,
        "exit_order_type": "market",
        "exit_time_in_force": "ioc",
    }


def _portfolio_spec(
    loadout: StrategyLoadout,
    *,
    strategy_name: str,
) -> dict[str, object]:
    return {
        "strategy_name": strategy_name,
        "symbol": loadout.symbol,
        "timeframe": loadout.timeframe,
        "strategy_params": {
            "strategy": loadout.strategy_name,
            **_effective_strategy_params(loadout),
        },
        "exits": _effective_exits(loadout),
        "risk": _effective_risk(loadout),
        "execution": _effective_execution(loadout),
    }


def portfolio_fingerprint(spec: Mapping[str, object]) -> str:
    """Return a stable digest of execution-affecting portfolio settings."""
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
