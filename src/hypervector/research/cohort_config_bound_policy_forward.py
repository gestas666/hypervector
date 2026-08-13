"""Bind sparse eligible-signal telemetry to an exact runtime exit contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isclose, isfinite

from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)
from hypervector.research.cohort_eligible_policy_forward import (
    EligiblePolicyForwardSpec,
    build_eligible_policy_forward_report,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)
from hypervector.research.cohort_live_audit_values import event_rows, payload, timestamp
from hypervector.research.cohort_observer_exact_books import (
    select_compatible_report_only_observer_runs,
)

Record = Mapping[str, object]
_STRESS_SCHEMA = "v49_portfolio_friction_stress_v1"
_FRICTION_FIELDS = (
    "round_trip_taker_fee",
    "live_entry_slippage_p99",
    "live_adverse_exit_slippage_p99",
    "visible_depth_p99",
)


@dataclass(frozen=True)
class ConfigBoundPolicyForwardBinding:
    """Select one exact provider-symbol and account-sizing stress scenario."""

    strategy_id: str
    candidate_strategy_id: str
    symbol: str
    account_value_usd: float

    def __post_init__(self) -> None:
        """Reject incomplete identities and invalid account values."""
        for value, label in (
            (self.strategy_id, "strategy id"),
            (self.candidate_strategy_id, "candidate strategy id"),
            (self.symbol, "symbol"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.strategy_id == self.candidate_strategy_id:
            raise ValueError("candidate strategy id must differ from source")
        _positive_number(self.account_value_usd, "account value")


def build_config_bound_policy_forward_report(
    records: Sequence[Record],
    *,
    base_config: MultiAssetLiveConfig,
    runtime_config: MultiAssetLiveConfig,
    stress_report: Record,
    binding: ConfigBoundPolicyForwardBinding,
    run_id: str,
    funding_evidence: EligiblePolicyFundingEvidence | None = None,
) -> dict[str, object]:
    """Track eligible signals using exact config and source-bound stress costs."""
    selected, identities = select_compatible_report_only_observer_runs(records, run_id)
    identity = _runtime_identity(selected, runtime_config, run_id)
    provider, asset = _bound_route(base_config, runtime_config, binding)
    execution = provider.execution_for(binding.symbol)
    _require_supported_execution(provider, binding.symbol)
    route, friction = _stress_route(stress_report, base_config, binding)
    _require_route_parity(route, execution.stop_bps, execution.maximum_hold_seconds)
    enriched = _enrich_candidate_contract(
        selected,
        run_id=run_id,
        binding=binding,
        stop_bps=_positive_number(execution.stop_bps, "configured stop"),
        maximum_hold_seconds=execution.maximum_hold_seconds,
    )
    spec = _spec(
        identity,
        runtime_config,
        asset,
        execution.maximum_hold_seconds,
        route,
        friction,
        binding,
        run_id,
    )
    report = build_eligible_policy_forward_report(
        enriched,
        spec=spec,
        funding_evidence=funding_evidence,
    )
    return _annotate(
        report,
        runtime_config,
        stress_report,
        friction,
        tuple(str(identity.get("run_id")) for identity in identities),
    )


def _runtime_identity(
    records: Sequence[Record], config: MultiAssetLiveConfig, run_id: str
) -> Record:
    identities = [
        row
        for row in event_rows(records, "configuration_identity")
        if row.get("run_id") == run_id
    ]
    if len(identities) != 1:
        raise ValueError("runtime configuration identity must be unique")
    identity = identities[0]
    fingerprint = config.profile_fingerprint
    if identity.get("profile_fingerprint") != fingerprint:
        raise ValueError("runtime profile fingerprint differs from bound config")
    if payload(identity).get("profile_fingerprint") != fingerprint:
        raise ValueError("runtime profile fingerprint payload is inconsistent")
    return identity


def _bound_route(
    base: MultiAssetLiveConfig,
    runtime: MultiAssetLiveConfig,
    binding: ConfigBoundPolicyForwardBinding,
) -> tuple[StrategyProviderConfig, AssetLiveConfig]:
    if base.profile_id != runtime.profile_id:
        raise ValueError("base and runtime profile ids differ")
    base_provider = _provider(base, binding)
    runtime_provider = _provider(runtime, binding)
    if base_provider != runtime_provider:
        raise ValueError("observer provider contract differs from base profile")
    base_asset = _asset(base, binding.symbol)
    runtime_asset = _asset(runtime, binding.symbol)
    if _asset_contract(base_asset) != _asset_contract(runtime_asset):
        raise ValueError("observer asset contract differs from base profile")
    if base.maximum_positions != runtime.maximum_positions:
        raise ValueError("observer portfolio capacity differs from base profile")
    return runtime_provider, runtime_asset


def _provider(
    config: MultiAssetLiveConfig, binding: ConfigBoundPolicyForwardBinding
) -> StrategyProviderConfig:
    matches = [
        provider
        for provider in config.providers
        if provider.strategy_id == binding.strategy_id
        and binding.symbol in provider.symbols
    ]
    if len(matches) != 1:
        raise ValueError("config-bound provider-symbol route must be unique")
    provider = matches[0]
    if binding.symbol not in provider.execution_symbols:
        raise ValueError("config-bound provider-symbol route is not executable")
    return provider


def _asset(config: MultiAssetLiveConfig, symbol: str) -> AssetLiveConfig:
    matches = [asset for asset in config.assets if asset.symbol == symbol]
    if len(matches) != 1:
        raise ValueError("config-bound asset must be unique")
    return matches[0]


def _asset_contract(asset: AssetLiveConfig) -> tuple[object, ...]:
    return (
        asset.symbol,
        asset.sides,
        asset.leverage,
        asset.venue_max_leverage,
        asset.margin_fraction,
        asset.max_notional_usd,
        asset.stop_bps,
        asset.maximum_hold_seconds,
    )


def _require_supported_execution(provider: StrategyProviderConfig, symbol: str) -> None:
    execution = provider.execution_for(symbol)
    if (
        execution.entry_liquidity != "taker_ioc"
        or execution.stop_policy != "fixed_bps"
        or execution.stop_bps is None
        or execution.target_policy != "none"
        or execution.maximum_hold_policy != "fixed"
        or execution.maximum_hold_seconds % 60
    ):
        raise ValueError(
            "config-bound policy forward supports fixed-stop/no-target routes"
        )


def _stress_route(
    report: Record,
    config: MultiAssetLiveConfig,
    binding: ConfigBoundPolicyForwardBinding,
) -> tuple[Record, dict[str, float]]:
    if report.get("schema_version") != _STRESS_SCHEMA:
        raise ValueError("stress report schema is not v49")
    if report.get("profile_id") != config.profile_id:
        raise ValueError("stress report profile id differs from base config")
    if report.get("profile_fingerprint") != config.profile_fingerprint:
        raise ValueError("stress report profile fingerprint differs from base config")
    scenario = _single(
        [
            row
            for row in _records(report.get("scenarios"), "stress scenarios")
            if _close(row.get("account_value_usd"), binding.account_value_usd)
        ],
        "stress account scenario",
    )
    slots = _mapping(scenario.get("asset_slots"), "stress asset slots")
    slot = _mapping(slots.get(binding.symbol), "stress symbol slot")
    route = _single(
        [
            row
            for row in _records(slot.get("routes"), "stress routes")
            if row.get("strategy_id") == binding.strategy_id
        ],
        "stress provider-symbol route",
    )
    components = _mapping(route.get("friction_components_bps"), "friction components")
    friction = {
        field: _nonnegative_number(components.get(field), field)
        for field in _FRICTION_FIELDS
    }
    return route, friction


def _require_route_parity(
    route: Record, stop_bps: float | None, maximum_hold_seconds: int
) -> None:
    if not _close(route.get("stop_bps"), stop_bps):
        raise ValueError("stress stop differs from runtime provider stop")
    expected_hours = maximum_hold_seconds / 3_600.0
    if not _close(route.get("maximum_hold_hours"), expected_hours):
        raise ValueError("stress hold differs from runtime provider hold")


def _spec(
    identity: Record,
    config: MultiAssetLiveConfig,
    asset: AssetLiveConfig,
    maximum_hold_seconds: int,
    route: Record,
    friction: Mapping[str, float],
    binding: ConfigBoundPolicyForwardBinding,
    run_id: str,
) -> EligiblePolicyForwardSpec:
    notional = _positive_number(route.get("planned_notional_usd"), "planned notional")
    if not isclose(notional, asset.max_notional_usd, abs_tol=1e-9):
        raise ValueError("stress notional differs from runtime asset cap")
    provider = _provider(config, binding)
    sizing = provider.entry_sizing(binding.symbol)
    if sizing is not None and not isclose(
        notional, sizing.max_notional_usd, abs_tol=1e-9
    ):
        raise ValueError("stress notional differs from provider sizing override")
    return EligiblePolicyForwardSpec(
        source_strategy_id=binding.strategy_id,
        candidate_strategy_id=binding.candidate_strategy_id,
        symbol=binding.symbol,
        source_run_id=run_id,
        cutoff_time_ms=int(timestamp(identity).timestamp() * 1_000),
        stop_bps=_positive_number(route.get("stop_bps"), "route stop"),
        maximum_hold_minutes=maximum_hold_seconds // 60,
        modeled_round_trip_friction_bps=sum(friction.values()),
        notional_usd=notional,
        maximum_positions=config.maximum_positions,
    )


def _enrich_candidate_contract(
    records: Sequence[Record],
    *,
    run_id: str,
    binding: ConfigBoundPolicyForwardBinding,
    stop_bps: float,
    maximum_hold_seconds: int,
) -> tuple[dict[str, object], ...]:
    return tuple(
        _enrich_row(row, run_id, binding, stop_bps, maximum_hold_seconds)
        for row in records
    )


def _enrich_row(
    row: Record,
    run_id: str,
    binding: ConfigBoundPolicyForwardBinding,
    stop_bps: float,
    maximum_hold_seconds: int,
) -> dict[str, object]:
    output = dict(row)
    if row.get("run_id") != run_id or row.get("event_type") != "intent_routing":
        return output
    values = dict(payload(row))
    evaluations = _records(values.get("evaluations"), "routing evaluations")
    values["evaluations"] = [
        _enrich_evaluation(value, binding, stop_bps, maximum_hold_seconds)
        for value in evaluations
    ]
    output["payload"] = values
    return output


def _enrich_evaluation(
    evaluation: Record,
    binding: ConfigBoundPolicyForwardBinding,
    stop_bps: float,
    maximum_hold_seconds: int,
) -> dict[str, object]:
    output = dict(evaluation)
    if not (
        evaluation.get("strategy_id") == binding.strategy_id
        and evaluation.get("symbol") == binding.symbol
        and evaluation.get("eligible") is True
    ):
        return output
    readiness = dict(_mapping(evaluation.get("readiness"), "candidate readiness"))
    metrics = dict(_mapping(readiness.get("metrics"), "candidate metrics"))
    _insert_exact(metrics, "stop_bps", stop_bps)
    _insert_exact(metrics, "maximum_hold_seconds", maximum_hold_seconds)
    readiness["metrics"] = metrics
    output["readiness"] = readiness
    return output


def _insert_exact(values: dict[str, object], name: str, expected: float) -> None:
    existing = values.get(name)
    if existing is not None and not _close(existing, expected):
        raise ValueError(f"candidate {name} conflicts with runtime profile")
    values[name] = expected


def _annotate(
    report: dict[str, object],
    config: MultiAssetLiveConfig,
    stress_report: Record,
    friction: Mapping[str, float],
    compatible_run_ids: tuple[str, ...],
) -> dict[str, object]:
    contract = dict(_mapping(report.get("contract"), "forward contract"))
    contract.update(
        {
            "execution_contract_source": "runtime_profile_config",
            "profile_id": config.profile_id,
            "profile_fingerprint": config.profile_fingerprint,
            "friction_scope": "stacked_p99_excluding_funding",
            "friction_components_bps": dict(friction),
            "friction_evidence_schema": stress_report.get("schema_version"),
            "compatible_run_ids": list(compatible_run_ids),
            "compatible_run_count": len(compatible_run_ids),
            "continuation_policy": "exact_contract_report_only_restarts",
        }
    )
    output = dict(report)
    output["mode"] = "cohort_config_bound_eligible_policy_forward_report"
    output["contract"] = contract
    limitations = list(_strings(report.get("limitations"), "limitations"))
    limitations.append(
        "stacked p99 slippage/depth costs are conservative and not conditioned on this entry"
    )
    output["limitations"] = limitations
    return output


def _single(values: Sequence[Record], label: str) -> Record:
    if len(values) != 1:
        raise ValueError(f"{label} must be unique")
    return values[0]


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(_mapping(row, f"{label} row") for row in value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must contain strings")
    return tuple(item for item in value if isinstance(item, str))


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _positive_number(value: object, label: str) -> float:
    result = _nonnegative_number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return result


def _close(value: object, expected: object) -> bool:
    try:
        left = _nonnegative_number(value, "comparison value")
        right = _nonnegative_number(expected, "comparison expected")
    except ValueError:
        return False
    return isclose(left, right, abs_tol=1e-9)
