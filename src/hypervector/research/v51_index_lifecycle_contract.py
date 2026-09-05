"""Source-bound v51 index lifecycle replay contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import cast

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.hip3_breakout_shadow_specs import (
    SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC,
    Hip3BreakoutShadowSpec,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    HIP3_INDEX_FRESH15_V3_STRATEGY,
)
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)
from hypervector.research.hip3_shadow_execution_contract import (
    bind_live_execution_contract,
)

_PROFILE = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
_SPECS = {row.symbol: row for row in (SP500_SHADOW_SPEC, SPCX_SHADOW_SPEC)}
_ACCOUNT_VALUE_USD = 5_000.0
_STOP_BPS = 80.0
_HOLD_MINUTES = 1_440


@dataclass(frozen=True)
class V51IndexLifecycleContract:
    """Verified v51 route, sizing, cost, and replay configuration."""

    symbol: str
    profile_id: str
    profile_fingerprint: str
    provider_id: str
    notional_usd: float
    nominal_residual_bps_per_side: float
    stress_extra_bps_per_side: float
    exit_slippage_evidence_scope: str
    source_evidence: dict[str, dict[str, object]]
    replay_config: Hip3ShadowLifecycleConfig


def load_v51_index_lifecycle_contract(
    config_path: Path,
    stress_path: Path,
    symbol: str,
) -> V51IndexLifecycleContract:
    """Load one exact authority-none v51 index replay contract."""
    spec = _spec(symbol)
    config = load_multi_asset_live_config(config_path, mode="observe")
    if config.profile_id != _PROFILE:
        raise ValueError("index lifecycle requires the exact v51 profile")
    report = _json_object(stress_path, "v51 stress evidence")
    _require_report_identity(report, config.profile_id, config.profile_fingerprint)
    _require_source_inputs(report, config_path)
    provider = next(
        (row for row in config.providers if row.strategy_id == spec.provider_id), None
    )
    if provider is None:
        raise ValueError("v51 index lifecycle provider is missing")
    asset = next((row for row in config.assets if row.symbol == symbol), None)
    if asset is None:
        raise ValueError("v51 index lifecycle asset is missing")
    _require_live_route(provider, asset, symbol)
    route = _stress_route(report, symbol)
    fee, stress, scope, notional = _route_costs(route)
    replay = _replay_config(spec, fee, stress, notional, stress_path, config_path)
    return V51IndexLifecycleContract(
        symbol,
        config.profile_id,
        config.profile_fingerprint,
        spec.provider_id,
        notional,
        0.0,
        stress,
        scope,
        {"config": file_evidence(config_path), "stress": file_evidence(stress_path)},
        replay,
    )


def _require_live_route(
    provider: StrategyProviderConfig, asset: AssetLiveConfig, symbol: str
) -> None:
    if asset.leverage != 10.0 or asset.margin_fraction != 0.1:
        raise ValueError("v51 index sizing contract is inconsistent")
    if asset.max_notional_usd != _ACCOUNT_VALUE_USD:
        raise ValueError("v51 index notional cap is inconsistent")
    if provider.sides != frozenset({"long", "short"}):
        raise ValueError("v51 index sides are inconsistent")
    long = provider.execution_for(symbol, "long")
    short = provider.execution_for(symbol, "short")
    if long != short:
        raise ValueError("v51 index execution contract must be symmetric")
    expected = (
        long.stop_policy == "fixed_bps"
        and long.stop_bps == _STOP_BPS
        and long.target_policy == "none"
        and long.maximum_hold_seconds == _HOLD_MINUTES * 60
        and long.profit_lock_policy == "completed_bar_trailing"
        and long.profit_lock_activation_bps == 100.0
        and long.profit_lock_floor_bps == 40.0
        and long.profit_lock_giveback_bps == 80.0
    )
    if not expected:
        raise ValueError("v51 index execution contract is inconsistent")


def _route_costs(
    route: Mapping[str, object],
) -> tuple[float, float, str, float]:
    if _number(route.get("stop_bps"), "stop") != _STOP_BPS:
        raise ValueError("v51 index stress stop is inconsistent")
    if _number(route.get("maximum_hold_hours"), "maximum hold") != 24.0:
        raise ValueError("v51 index stress hold is inconsistent")
    if route.get("strategy_id") != HIP3_INDEX_FRESH15_V3_STRATEGY:
        raise ValueError("v51 index stress strategy is inconsistent")
    components = _mapping(route.get("friction_components_bps"), "friction")
    fee = _number(components.get("round_trip_taker_fee"), "round-trip fee") / 2.0
    entry = _number(components.get("live_entry_slippage_p99"), "entry slippage")
    adverse = _number(components.get("live_adverse_exit_slippage_p99"), "exit slippage")
    evidence = _mapping(route.get("execution_friction"), "execution friction")
    scope = _text(evidence.get("exit_evidence_scope"), "exit evidence scope")
    notional = _number(route.get("planned_notional_usd"), "planned notional")
    if notional != _ACCOUNT_VALUE_USD:
        raise ValueError("v51 index stress notional is inconsistent")
    return fee, max(entry, adverse), scope, notional


def _replay_config(
    spec: Hip3BreakoutShadowSpec,
    fee: float,
    stress: float,
    notional: float,
    source: Path,
    execution_source: Path,
) -> Hip3ShadowLifecycleConfig:
    base = Hip3ShadowLifecycleConfig(
        symbol=spec.symbol,
        provider_id=spec.provider_id,
        profile_id=spec.profile_id,
        ledger_profile_id=spec.ledger_profile_id,
        signal_config=spec.config,
        fee_bps_per_side=fee,
        residual_latency_bps_per_side=0.0,
        stress_extra_bps_per_side=stress,
        notional_usd=notional,
        maximum_book_lateness_ms=15_000,
        maximum_mark_gap_ms=5_000,
        maximum_hold_minutes=_HOLD_MINUTES,
        friction_source=f"v51_source_bound_stress:{source}",
    )
    return bind_live_execution_contract(base, execution_source)


def _stress_route(report: Mapping[str, object], symbol: str) -> Mapping[str, object]:
    scenarios = _sequence(report.get("scenarios"), "stress scenarios")
    scenario = next(
        (
            _mapping(row, "stress scenario")
            for row in scenarios
            if _mapping(row, "stress scenario").get("account_value_usd")
            == _ACCOUNT_VALUE_USD
        ),
        None,
    )
    if scenario is None:
        raise ValueError("v51 $5,000 stress scenario is missing")
    assets = _mapping(scenario.get("asset_slots"), "stress assets")
    slot = _mapping(assets.get(symbol), "stress asset")
    routes = _sequence(slot.get("routes"), "stress routes")
    if len(routes) != 1:
        raise ValueError("v51 index stress route is ambiguous")
    return _mapping(routes[0], "stress route")


def _require_report_identity(
    report: Mapping[str, object], profile: str, fingerprint: str
) -> None:
    contract = _mapping(report.get("contract"), "stress contract")
    safe = (
        report.get("profile_id") == profile
        and report.get("profile_fingerprint") == fingerprint
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("runtime_strategy_changed") is False
        and contract.get("automatic_sizing_change") is False
    )
    if not safe:
        raise ValueError("v51 stress evidence identity or authority is inconsistent")


def _require_source_inputs(report: Mapping[str, object], config_path: Path) -> None:
    inputs = _mapping(report.get("inputs"), "stress inputs")
    _require_recorded_file(inputs, config_path)
    friction = next(
        (
            Path(str(_mapping(row, "input evidence").get("path")))
            for row in inputs.values()
            if "execution_friction_stress"
            in str(_mapping(row, "input evidence").get("path"))
        ),
        None,
    )
    if friction is None:
        raise ValueError("v51 stress has no execution-friction source")
    _require_recorded_file(inputs, friction)


def _require_recorded_file(inputs: Mapping[str, object], path: Path) -> None:
    expected = file_evidence(path)
    matches = [
        _mapping(row, "input evidence")
        for row in inputs.values()
        if _mapping(row, "input evidence").get("path") == str(path)
    ]
    if len(matches) != 1 or any(
        matches[0].get(key) != expected.get(key) for key in ("bytes", "sha256")
    ):
        raise ValueError(f"v51 stress input evidence changed: {path}")


def _spec(symbol: str) -> Hip3BreakoutShadowSpec:
    spec = _SPECS.get(symbol)
    if spec is None:
        raise ValueError("v51 index lifecycle symbol must be SP500 or SPCX")
    return spec


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, label)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output) or output < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return output


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value
