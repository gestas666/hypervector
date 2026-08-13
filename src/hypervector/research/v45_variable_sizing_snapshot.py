"""Report-only counterfactual sizing snapshots for exact v45 entries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)
from hypervector.research.v45_poststart_acceptance import (
    V45_ROUTE_NATIVE_SIZING_FEATURES,
)

Record = Mapping[str, object]
EntryKey = tuple[str, str, str, int]
_PROFILE = "multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45"
_TIERS = (0.75, 1.0, 1.25)
_ACCOUNTS = (500.0, 5_000.0)


@dataclass
class _SizingScan:
    evaluations: int = 0
    eligible_evaluations: int = 0
    eligible_not_routed: int = 0
    candidates: dict[str, dict[str, object]] = field(default_factory=dict)
    route_counts: dict[str, int] = field(default_factory=dict)


def build_v45_variable_sizing_snapshot(
    rows: Iterable[Record],
    config: MultiAssetLiveConfig,
) -> dict[str, object]:
    """Freeze eligible decision features and three no-authority sizing tiers."""
    _validate_config(config)
    scan = _SizingScan()
    for row in rows:
        if row.get("event_type") != "intent_routing":
            continue
        _scan_routing_row(row, config, scan)
    return _snapshot_payload(config, scan)


def _snapshot_payload(
    config: MultiAssetLiveConfig,
    scan: _SizingScan,
) -> dict[str, object]:
    return {
        "schema_version": "v45_variable_sizing_snapshot_v1",
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
        "tier_authority": "counterfactual_only",
        "selected_tier_policy": "withheld_pending_forward_outcomes",
        "leverage_policy": {
            "mode": "fixed_isolated",
            "configured_leverage": _fixed_leverage(config),
            "variable_leverage_authorized": False,
        },
        "tier_input_policy": {
            "route_native_features_only": True,
            "canonical_regime_scaling": (
                "withheld_pending_symbol_side_horizon_calibration"
            ),
        },
        "evaluations": scan.evaluations,
        "evaluations_by_route": dict(sorted(scan.route_counts.items())),
        "eligible_evaluations": scan.eligible_evaluations,
        "eligible_not_routed": scan.eligible_not_routed,
        "eligible_candidates": len(scan.candidates),
        "candidates": [scan.candidates[key] for key in sorted(scan.candidates)],
        "configured_route_scenarios": _configured_route_scenarios(config),
        "limitations": [
            "the snapshot records hypotheses and cannot resize an order",
            "no tier is selected before compatible after-cost outcomes exist",
            "counterfactual stop loss excludes gap-through and size-dependent slippage",
        ],
    }


def _fixed_leverage(config: MultiAssetLiveConfig) -> float:
    """Return the sole configured leverage or reject an ambiguous policy."""
    values = {asset.leverage for asset in config.assets}
    if len(values) != 1:
        raise ValueError("v45 sizing snapshot requires one fixed asset leverage")
    return values.pop()


def _configured_route_scenarios(
    config: MultiAssetLiveConfig,
) -> list[dict[str, object]]:
    """Describe fixed-leverage tier capacity without manufacturing an entry."""
    rows: list[dict[str, object]] = []
    for provider in config.providers:
        for symbol in provider.execution_symbols:
            for side in provider.executable_sides(symbol):
                _bound_provider, asset = _route_config(
                    config, provider.strategy_id, symbol, side
                )
                policy = provider.entry_sizing(symbol, side) or CohortEntrySizing(
                    asset.margin_fraction,
                    asset.max_notional_usd,
                )
                rows.append(
                    {
                        "strategy_id": provider.strategy_id,
                        "symbol": symbol,
                        "side": side,
                        "base_margin_fraction": policy.margin_fraction,
                        "maximum_notional_usd": policy.max_notional_usd,
                        "leverage": asset.leverage,
                        "stop_bps": _stop_bps(provider),
                        "account_scenarios": _scenarios(policy, asset, provider),
                    }
                )
    return sorted(
        rows, key=lambda row: str((row["strategy_id"], row["symbol"], row["side"]))
    )


def _scan_routing_row(
    row: Record,
    config: MultiAssetLiveConfig,
    scan: _SizingScan,
) -> None:
    _validate_row_identity(row, config)
    routed_entries = _routed_entry_keys(row)
    matched_entries: set[EntryKey] = set()
    for evaluation in _evaluations(row):
        scan.evaluations += 1
        route = _route(evaluation)
        scan.route_counts[route] = scan.route_counts.get(route, 0) + 1
        entry_key = _eligible_entry_key(evaluation)
        if entry_key is None:
            continue
        scan.eligible_evaluations += 1
        if entry_key not in routed_entries:
            scan.eligible_not_routed += 1
            continue
        matched_entries.add(entry_key)
        _store_candidate(scan, _candidate(evaluation, row, config))
    unmatched = routed_entries.difference(matched_entries)
    if unmatched:
        raise ValueError(f"v45 routed entries lack eligible evaluations: {unmatched}")


def _store_candidate(scan: _SizingScan, candidate: dict[str, object]) -> None:
    event_id = str(candidate["event_id"])
    prior = scan.candidates.get(event_id)
    if prior is not None and prior != candidate:
        raise ValueError(f"v45 sizing candidate conflict: {event_id}")
    scan.candidates[event_id] = candidate


def _candidate(
    evaluation: Record,
    row: Record,
    config: MultiAssetLiveConfig,
) -> dict[str, object]:
    action = _text(evaluation.get("decision_action"), "decision_action")
    if action not in {"enter_long", "enter_short"}:
        raise ValueError("eligible v45 sizing evaluation must be an entry")
    side = action.removeprefix("enter_")
    strategy = _text(evaluation.get("strategy_id"), "strategy_id")
    symbol = _text(evaluation.get("symbol"), "symbol")
    decision = _integer(evaluation.get("decision_time_ms"), "decision_time_ms")
    run_id = _text(row.get("run_id"), "source run_id")
    run_fingerprint = _text(row.get("run_fingerprint"), "source run fingerprint")
    route = f"{strategy}|{symbol}"
    features = _features(evaluation, route)
    provider, asset = _route_config(config, strategy, symbol, side)
    policy = provider.entry_sizing(symbol, side) or CohortEntrySizing(
        asset.margin_fraction, asset.max_notional_usd
    )
    return {
        "event_id": f"{run_id}|{route}|{side}|{decision}",
        "source_run_id": run_id,
        "source_run_fingerprint": run_fingerprint,
        "strategy_id": strategy,
        "symbol": symbol,
        "side": side,
        "decision_time_ms": decision,
        "features": features,
        "selected_tier": None,
        "base_margin_fraction": policy.margin_fraction,
        "maximum_notional_usd": policy.max_notional_usd,
        "leverage": asset.leverage,
        "stop_bps": _stop_bps(provider),
        "account_scenarios": _scenarios(policy, asset, provider),
    }


def _scenarios(
    policy: CohortEntrySizing,
    asset: AssetLiveConfig,
    provider: StrategyProviderConfig,
) -> dict[str, object]:
    output: dict[str, object] = {}
    stop_bps = _stop_bps(provider)
    for account in _ACCOUNTS:
        base = policy.planned_notional(
            account_value_usd=account,
            leverage=asset.leverage,
        )
        tiers = {
            _tier_key(tier): _tier(base, tier, policy, asset.leverage, stop_bps)
            for tier in _TIERS
        }
        output[str(int(account))] = {
            "account_value_usd": account,
            "base_notional_usd": base,
            "tiers": tiers,
        }
    return output


def _tier(
    base: float,
    tier: float,
    policy: CohortEntrySizing,
    leverage: float,
    stop_bps: float,
) -> dict[str, object]:
    requested = base * tier
    notional = min(requested, policy.max_notional_usd)
    return {
        "requested_multiplier": tier,
        "effective_multiplier": notional / base,
        "notional_usd": notional,
        "isolated_margin_usd": notional / leverage,
        "gross_stop_loss_usd": notional * stop_bps / 10_000.0,
        "cap_binding": notional < requested,
    }


def _features(evaluation: Record, route: str) -> dict[str, object]:
    required = V45_ROUTE_NATIVE_SIZING_FEATURES.get(route)
    if required is None:
        raise ValueError(f"unsupported v45 sizing route: {route}")
    readiness = _mapping(evaluation.get("readiness"), f"{route} readiness")
    metrics = _mapping(readiness.get("metrics"), f"{route} metrics")
    missing = tuple(name for name in required if metrics.get(name) is None)
    if missing:
        raise ValueError(f"v45 sizing features missing for {route}: {missing}")
    return {name: metrics[name] for name in required}


def _route_config(
    config: MultiAssetLiveConfig,
    strategy: str,
    symbol: str,
    side: str,
) -> tuple[StrategyProviderConfig, AssetLiveConfig]:
    providers = tuple(
        provider
        for provider in config.providers
        if provider.strategy_id == strategy and symbol in provider.execution_symbols
    )
    assets = tuple(asset for asset in config.assets if asset.symbol == symbol)
    if len(providers) != 1 or len(assets) != 1:
        raise ValueError(f"v45 sizing route identity is ambiguous: {strategy}|{symbol}")
    if side not in providers[0].executable_sides(symbol):
        raise ValueError(
            f"v45 sizing side is not executable: {strategy}|{symbol}|{side}"
        )
    return providers[0], assets[0]


def _validate_config(config: MultiAssetLiveConfig) -> None:
    if config.profile_id != _PROFILE or config.mode != "observe":
        raise ValueError("v45 sizing snapshot requires exact observe configuration")


def _validate_row_identity(row: Record, config: MultiAssetLiveConfig) -> None:
    if row.get("profile_id") != config.profile_id:
        raise ValueError("v45 sizing ledger profile is inconsistent")
    if row.get("profile_fingerprint") != config.profile_fingerprint:
        raise ValueError("v45 sizing ledger fingerprint is inconsistent")
    observe_contract = (
        row.get("execution_authority") == "none"
        and row.get("execution_mode") == "observe"
        and row.get("effective_mode") == "OBSERVE ONLY"
        and row.get("live_armed") is False
    )
    if not observe_contract:
        raise ValueError("v45 sizing source must remain no-authority observe data")
    _text(row.get("run_id"), "source run_id")
    _text(row.get("run_fingerprint"), "source run fingerprint")


def _eligible_entry_key(evaluation: Record) -> EntryKey | None:
    if evaluation.get("eligible") is not True:
        return None
    action = _text(evaluation.get("decision_action"), "decision_action")
    if action not in {"enter_long", "enter_short"}:
        raise ValueError("eligible v45 sizing evaluation must be an entry")
    return (
        _text(evaluation.get("strategy_id"), "strategy_id"),
        _text(evaluation.get("symbol"), "symbol"),
        action.removeprefix("enter_"),
        _integer(evaluation.get("decision_time_ms"), "decision_time_ms"),
    )


def _routed_entry_keys(row: Record) -> frozenset[EntryKey]:
    payload = _mapping(row.get("payload"), "intent routing payload")
    raw = payload.get("actions")
    if not isinstance(raw, list):
        raise ValueError("v45 sizing routing actions must be a list")
    entries = tuple(
        _routed_entry_key(_mapping(value, "routing action"))
        for value in raw
        if _mapping(value, "routing action").get("action") == "enter"
    )
    if len(entries) != len(set(entries)):
        raise ValueError("v45 sizing routing actions contain duplicate entries")
    return frozenset(entries)


def _routed_entry_key(action: Record) -> EntryKey:
    side = _text(action.get("side"), "routing side")
    if side not in {"long", "short"}:
        raise ValueError("v45 sizing routing side must be long or short")
    return (
        _text(action.get("strategy_id"), "routing strategy_id"),
        _text(action.get("symbol"), "routing symbol"),
        side,
        _integer(action.get("decision_time_ms"), "routing decision_time_ms"),
    )


def _evaluations(row: Record) -> tuple[Record, ...]:
    payload = _mapping(row.get("payload"), "intent routing payload")
    raw = payload.get("evaluations")
    if not isinstance(raw, list):
        raise ValueError("v45 sizing evaluations must be a list")
    return tuple(_mapping(value, "provider evaluation") for value in raw)


def _route(evaluation: Record) -> str:
    strategy = _text(evaluation.get("strategy_id"), "strategy_id")
    symbol = _text(evaluation.get("symbol"), "symbol")
    return f"{strategy}|{symbol}"


def _stop_bps(provider: StrategyProviderConfig) -> float:
    contract = provider.execution
    value = contract.stop_bps or contract.maximum_stop_bps
    if value is None:
        raise ValueError(f"v45 provider stop is not bounded: {provider.strategy_id}")
    return value


def _tier_key(value: float) -> str:
    return str(value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"v45 sizing {label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"v45 sizing {label} must be a nonnegative integer")
    return value
