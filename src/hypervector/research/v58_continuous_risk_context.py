"""Source-bound exposure context for the V58 research observer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

Record = Mapping[str, object]

_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_SCHEMA = "v58_eight_asset_growth_stress_v1"


@dataclass(frozen=True)
class RiskContext:
    """Validated V58 exposure and simultaneous-stop evidence."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_risk_context(config_path: Path, stress_path: Path) -> RiskContext:
    """Load the exact config-bound frozen V58 stress evidence."""
    config_evidence = file_evidence(config_path)
    config = load_multi_asset_live_config(config_path, mode="observe")
    stress, stress_evidence = _read_json(stress_path)
    _require_stress_contract(stress, config, config_path, config_evidence)
    scenario = _single_scenario(stress)
    account_value = _positive_number(scenario.get("account_value_usd"), "account value")
    slots = _slot_rows(scenario.get("asset_slots"), config, account_value)
    payload = _risk_payload(stress, scenario, slots, account_value, config)
    if file_evidence(config_path) != config_evidence:
        raise ValueError("V58 config changed during risk context evaluation")
    return RiskContext(
        payload,
        {
            "config": {"path": str(config_path.resolve()), **config_evidence},
            "stress": {"path": str(stress_path.resolve()), **stress_evidence},
        },
    )


def risk_context_payload(context: RiskContext) -> dict[str, object]:
    """Serialize V58 risk evidence without sizing or execution authority."""
    return {
        **context.payload,
        "joint_loss_probability_claim": False,
        "loss_ceiling_claim": False,
        "sizing_input": False,
        "automatic_sizing_change": False,
        "execution_authority": context.execution_authority,
    }


def current_equity_risk_context_payload(
    context: RiskContext,
    *,
    actual_account_value_usd: float,
    sizing_reference_equity_usd: float,
    observed_at_utc: str,
    fresh: bool,
) -> dict[str, object]:
    """Add point-in-time account-relative exposure without changing sizing."""
    payload = risk_context_payload(context)
    reference = _positive_number(payload.get("account_value_usd"), "account value")
    sizing_reference = _positive_number(sizing_reference_equity_usd, "sizing reference")
    actual = _positive_number(actual_account_value_usd, "actual account value")
    if not math.isclose(reference, sizing_reference, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("V58 risk and venue sizing references differ")
    if not isinstance(observed_at_utc, str) or not observed_at_utc.strip():
        raise ValueError("V58 actual account observation time is invalid")
    if not isinstance(fresh, bool):
        raise ValueError("V58 actual account freshness must be boolean")
    loss = _positive_number(payload.get("stacked_p99_stop_wave_loss_usd"), "loss")
    margin = _positive_number(payload.get("maximum_margin_usd"), "margin")
    gross = _positive_number(
        payload.get("maximum_gross_notional_usd"), "gross notional"
    )
    payload.update(
        {
            "sizing_reference_equity_usd": reference,
            "actual_account_value_usd": actual,
            "actual_account_value_observed_at_utc": observed_at_utc,
            "actual_account_value_fresh": fresh,
            "stacked_p99_stop_wave_loss_pct_sizing_reference": loss / reference * 100.0,
            "stacked_p99_stop_wave_loss_pct_actual_account": loss / actual * 100.0,
            "maximum_margin_pct_actual_account": margin / actual * 100.0,
            "maximum_gross_notional_pct_actual_account": gross / actual * 100.0,
        }
    )
    return payload


def _read_json(path: Path) -> tuple[Record, dict[str, object]]:
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "V58 stress artifact")
    return payload, file_evidence(path)


def _require_stress_contract(
    stress: Record,
    config: MultiAssetLiveConfig,
    config_path: Path,
    config_evidence: Record,
) -> None:
    expected = {
        "schema_version": _SCHEMA,
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": config.profile_fingerprint,
    }
    if any(stress.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 stress profile identity is invalid")
    contract = _mapping(stress.get("contract"), "V58 stress contract")
    safe = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_sizing_change": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }
    if any(contract.get(field) != value for field, value in safe.items()):
        raise ValueError("V58 stress authority contract is invalid")
    _require_config_evidence(stress, config_path, config_evidence)


def _require_config_evidence(
    stress: Record, config_path: Path, current: Record
) -> None:
    inputs = _mapping(stress.get("inputs"), "V58 stress inputs")
    matches = [
        _mapping(value, "V58 config evidence")
        for raw_path, value in inputs.items()
        if Path(raw_path).resolve() == config_path.resolve()
    ]
    if len(matches) != 1:
        raise ValueError("V58 stress config evidence is missing or duplicated")
    expected = {"sha256": current.get("sha256"), "bytes": current.get("bytes")}
    if any(matches[0].get(field) != value for field, value in expected.items()):
        raise ValueError("V58 stress config evidence does not match current config")


def _single_scenario(stress: Record) -> Record:
    value = stress.get("scenarios")
    if not isinstance(value, list) or len(value) != 1:
        raise ValueError("V58 stress must contain one exact scenario")
    return _mapping(value[0], "V58 stress scenario")


def _slot_rows(
    value: object, config: MultiAssetLiveConfig, account_value: float
) -> list[dict[str, object]]:
    slots = _mapping(value, "V58 stress asset slots")
    assets = {asset.symbol: asset for asset in config.assets}
    if set(slots) != set(assets):
        raise ValueError("V58 stress asset slot set is incomplete or aliased")
    return [
        _slot_row(symbol, slots[symbol], assets[symbol], config, account_value)
        for symbol in config.symbols
    ]


def _slot_row(
    symbol: str,
    value: object,
    asset: AssetLiveConfig,
    config: MultiAssetLiveConfig,
    account_value: float,
) -> dict[str, object]:
    slot = _mapping(value, f"{symbol} stress slot")
    raw_routes = slot.get("routes")
    if not isinstance(raw_routes, list) or not raw_routes:
        raise ValueError(f"{symbol} stress routes must be a non-empty array")
    providers = [
        provider
        for provider in config.providers
        if symbol in provider.execution_symbols
    ]
    routes = [_mapping(value, f"{symbol} stress route") for value in raw_routes]
    expected_routes = {provider.strategy_id for provider in providers}
    if (
        len(routes) != len(expected_routes)
        or {row.get("strategy_id") for row in routes} != expected_routes
    ):
        raise ValueError(f"{symbol} stress route identity is incomplete or aliased")
    for route in routes:
        provider = next(
            row for row in providers if row.strategy_id == route["strategy_id"]
        )
        _require_route_contract(route, provider, asset, account_value)
    return _slot_payload(symbol, slot, routes, asset, account_value)


def _require_route_contract(
    route: Record,
    provider: StrategyProviderConfig,
    asset: AssetLiveConfig,
    account_value: float,
) -> None:
    sides = provider.executable_sides(asset.symbol)
    sizing = _maximum_sizing(provider, asset, sides, account_value)
    contract = provider.execution_for(asset.symbol)
    maximum_hold = contract.hard_maximum_hold_seconds or contract.maximum_hold_seconds
    stop_bps = contract.stop_bps or contract.maximum_stop_bps
    expected = {
        "sides": sorted(sides),
        "margin_fraction": sizing.margin_fraction,
        "planned_notional_usd": sizing.planned_notional(
            account_value_usd=account_value, leverage=asset.leverage
        ),
        "stop_bps": stop_bps,
        "maximum_hold_hours": maximum_hold / 3600.0,
    }
    if any(not _equal(route.get(field), value) for field, value in expected.items()):
        raise ValueError(f"{asset.symbol} stress route contract is inconsistent")


def _maximum_sizing(
    provider: StrategyProviderConfig,
    asset: AssetLiveConfig,
    sides: Sequence[str],
    account_value: float,
) -> CohortEntrySizing:
    fallback = CohortEntrySizing(asset.margin_fraction, asset.max_notional_usd)
    candidates = [
        provider.entry_sizing(asset.symbol, side) or fallback for side in sides
    ]
    return max(
        candidates,
        key=lambda sizing: sizing.planned_notional(
            account_value_usd=account_value, leverage=asset.leverage
        ),
    )


def _slot_payload(
    symbol: str,
    slot: Record,
    routes: Sequence[Record],
    asset: AssetLiveConfig,
    account_value: float,
) -> dict[str, object]:
    losses = [
        _positive_number(row.get("stacked_p99_stop_loss_usd"), "slot loss")
        for row in routes
    ]
    notionals = [
        _positive_number(row.get("planned_notional_usd"), "slot notional")
        for row in routes
    ]
    route_margins = [
        _positive_number(row.get("margin_fraction"), "route margin") for row in routes
    ]
    margin = _positive_number(slot.get("maximum_margin_fraction"), "slot margin")
    if not math.isclose(margin, max(route_margins), rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f"{symbol} slot margin does not reconcile to routes")
    maximum_loss = max(losses)
    worst = sorted(
        str(row["strategy_id"])
        for row, loss in zip(routes, losses)
        if math.isclose(loss, maximum_loss, rel_tol=1e-12, abs_tol=1e-12)
    )
    return {
        "symbol": symbol,
        "leverage": asset.leverage,
        "maximum_margin_fraction": margin,
        "maximum_margin_usd": account_value * margin,
        "maximum_notional_usd": max(notionals),
        "slot_p99_loss_usd": maximum_loss,
        "slot_p99_loss_pct_equity": maximum_loss / account_value * 100.0,
        "worst_loss_routes": worst,
        "route_count": len(routes),
    }


def _risk_payload(
    stress: Record,
    scenario: Record,
    slots: Sequence[Record],
    account_value: float,
    config: MultiAssetLiveConfig,
) -> dict[str, object]:
    margin = _positive_number(
        scenario.get("route_aware_maximum_margin_fraction"), "maximum margin"
    )
    loss = _positive_number(
        scenario.get("stacked_p99_stop_wave_loss_usd"), "stacked loss"
    )
    loss_pct = _positive_number(
        scenario.get("stacked_p99_stop_wave_loss_pct_equity"), "stacked loss pct"
    )
    capacity = _positive_integer(
        scenario.get("account_position_capacity"), "position capacity"
    )
    simultaneous = _positive_integer(
        scenario.get("maximum_simultaneous_positions"), "simultaneous positions"
    )
    if capacity != config.maximum_positions or simultaneous != len(config.assets):
        raise ValueError("V58 stress position capacity is inconsistent with config")
    _require_totals(slots, account_value, margin, loss, loss_pct)
    return {
        "account_value_usd": account_value,
        "account_position_capacity": capacity,
        "maximum_simultaneous_positions": simultaneous,
        "maximum_margin_fraction": margin,
        "maximum_margin_usd": account_value * margin,
        "maximum_gross_notional_usd": sum(
            float(row["maximum_notional_usd"]) for row in slots
        ),
        "stacked_p99_stop_wave_loss_usd": loss,
        "stacked_p99_stop_wave_loss_pct_equity": loss_pct,
        "asset_slots": [dict(row) for row in slots],
        "model_scope": "marginal_p99_components_stacked_not_joint_probability",
        "limitations": _limitations(stress),
    }


def _require_totals(
    slots: Sequence[Record],
    account_value: float,
    margin: float,
    loss: float,
    loss_pct: float,
) -> None:
    slot_margin = sum(float(row["maximum_margin_fraction"]) for row in slots)
    slot_loss = sum(float(row["slot_p99_loss_usd"]) for row in slots)
    if not math.isclose(slot_margin, margin, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("V58 stress margin total does not reconcile")
    if not math.isclose(slot_loss, loss, rel_tol=1e-12, abs_tol=1e-9):
        raise ValueError("V58 stress loss total does not reconcile")
    expected_pct = loss / account_value * 100.0
    if not math.isclose(expected_pct, loss_pct, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("V58 stress loss percentage does not reconcile")


def _limitations(stress: Record) -> list[str]:
    output = []
    for field in ("limitations", "evidence_limitations"):
        values = stress.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            raise ValueError(f"V58 stress {field} must be an array of text")
        output.extend(value.strip() for value in values if value.strip())
    return output


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive_number(value: object, label: str) -> float:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not math.isfinite(value) or float(value) <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return float(value)


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _equal(actual: object, expected: object) -> bool:
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(
            float(actual), expected, rel_tol=1e-12, abs_tol=1e-12
        )
    return actual == expected
