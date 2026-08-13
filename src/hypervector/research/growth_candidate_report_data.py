"""Shared candidate-route datasets for versioned growth reports."""

from __future__ import annotations

from collections.abc import Callable
import math
from typing import cast

JsonMap = dict[str, object]
StrategyLabel = Callable[[str], str]


def json_mapping(value: object, label: str) -> JsonMap:
    """Require a JSON-shaped mapping."""
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(JsonMap, value)


def json_sequence(value: object, label: str) -> list[object]:
    """Require a JSON-shaped sequence."""
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return value


def account_scenario(stress: JsonMap, account_value_usd: float) -> JsonMap:
    """Return the exact account-value scenario from friction evidence."""
    for raw in json_sequence(stress["scenarios"], "scenarios"):
        scenario = json_mapping(raw, "scenario")
        if math.isclose(float(scenario["account_value_usd"]), account_value_usd):
            return scenario
    raise ValueError(f"stress evidence lacks the ${account_value_usd:,.0f} scenario")


def candidate_routes(
    config: JsonMap,
    stress: JsonMap,
    strategy_label: StrategyLabel,
) -> list[JsonMap]:
    """Build one exact report row per provider-symbol route."""
    providers = _provider_map(config)
    leverage_by_asset = _asset_leverage(config)
    slots = json_mapping(account_scenario(stress, 5_000.0)["asset_slots"], "slots")
    rows: list[JsonMap] = []
    for asset, raw_slot in slots.items():
        slot = json_mapping(raw_slot, asset)
        for raw_route in json_sequence(slot["routes"], f"{asset}.routes"):
            route = json_mapping(raw_route, "route")
            strategy = str(route["strategy_id"])
            provider = providers[strategy]
            rows.append(
                _route_row(
                    asset,
                    route,
                    provider,
                    strategy,
                    strategy_label,
                    leverage_by_asset[asset],
                )
            )
    return rows


def candidate_capacity(config: JsonMap, stress: JsonMap, label: str) -> JsonMap:
    """Build exact $5K capacity and stacked-loss metrics."""
    scenario = account_scenario(stress, 5_000.0)
    assets = json_sequence(config["assets"], "assets")
    margin = sum(
        float(json_mapping(asset, "asset")["margin_fraction"]) for asset in assets
    )
    leverage = {float(json_mapping(asset, "asset")["leverage"]) for asset in assets}
    if len(leverage) != 1:
        raise ValueError(f"{label} report requires uniform leverage")
    first_asset = json_mapping(assets[0], "asset")
    return {
        "profile_id": config["profile"],
        "account_position_capacity": int(scenario["account_position_capacity"]),
        "usable_asset_slots": int(scenario["maximum_simultaneous_positions"]),
        "leverage": leverage.pop(),
        "margin_fraction_per_asset": float(first_asset["margin_fraction"]),
        "maximum_margin_fraction": margin,
        "p99_stop_wave_loss_usd": float(scenario["stacked_p99_stop_wave_loss_usd"]),
        "p99_stop_wave_fraction": float(
            scenario["stacked_p99_stop_wave_loss_pct_equity"]
        )
        / 100.0,
    }


def candidate_slot_risk(stress: JsonMap) -> list[JsonMap]:
    """Build one p99 stop-wave contribution row per asset."""
    scenario = account_scenario(stress, 5_000.0)
    slots = json_mapping(scenario["asset_slots"], "asset_slots")
    return [
        {
            "asset": asset,
            "p99_stop_loss_usd": json_mapping(raw, asset)["stacked_p99_slot_loss_usd"],
        }
        for asset, raw in slots.items()
    ]


def _provider_map(config: JsonMap) -> dict[str, JsonMap]:
    return {
        str(provider["strategy_id"]): provider
        for provider in (
            json_mapping(raw, "provider")
            for raw in json_sequence(config["providers"], "providers")
        )
    }


def _asset_leverage(config: JsonMap) -> dict[str, float]:
    return {
        str(asset["symbol"]): float(asset["leverage"])
        for asset in (
            json_mapping(raw, "asset")
            for raw in json_sequence(config["assets"], "assets")
        )
    }


def _route_row(
    asset: str,
    route: JsonMap,
    provider: JsonMap,
    strategy: str,
    strategy_label: StrategyLabel,
    leverage: float,
) -> JsonMap:
    return {
        "asset": asset,
        "strategy_id": strategy,
        "route_label": f"{strategy_label(strategy)} | {asset}",
        "timeframe": provider["timeframe"],
        "sides": "/".join(cast(list[str], route["sides"])),
        "leverage": leverage,
        "margin_fraction": float(route["margin_fraction"]),
        "notional_usd": float(route["planned_notional_usd"]),
        "p99_stop_loss_usd": float(route["stacked_p99_stop_loss_usd"]),
        "risk_contract": _exit_contract(provider),
    }


def _exit_contract(provider: JsonMap) -> str:
    execution = json_mapping(provider["execution"], "execution")
    stop = execution.get("stop_bps", execution.get("maximum_stop_bps"))
    target = execution.get("target_bps")
    if target is None and execution.get("target_r_multiple") is not None:
        primary = f"{float(execution['target_r_multiple']):g}R target"
    elif target is not None:
        primary = f"{float(target):g} bps target"
    else:
        primary = "strategy/opposite exit"
    fallback = float(execution["maximum_hold_seconds"]) / 3600.0
    hard = execution.get("hard_maximum_hold_seconds")
    fallback_text = (
        f"{fallback:g}h soft / {float(hard) / 3600.0:g}h hard"
        if hard is not None
        else f"{fallback:g}h fallback"
    )
    return f"{float(stop):g} bps stop / {primary} / {fallback_text}"
