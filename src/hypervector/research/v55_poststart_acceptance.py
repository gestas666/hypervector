"""Report-only technical acceptance for the additive v55 SPCX route."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.live.hip3_cash_open_gap_provider import (
    HIP3_SPCX_CASH_OPEN_STRATEGY,
)
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.cohort_live_audit_values import mapping, nonnegative_int
from hypervector.research.v39_poststart_acceptance import (
    _acceptance_checks as _shared_acceptance_checks,
)
from hypervector.research.v43_poststart_acceptance import (
    BtcSpecialistAcceptanceSpec,
    _check_reasons,
    _direction_scope_check,
    _require_flat_preflight,
)
from hypervector.research.v51_poststart_acceptance import (
    _bound_execution_plan_check,
)
from hypervector.research.v52_poststart_acceptance import _aware, _positive

Record = Mapping[str, object]
_PROFILE_ID = "multi_asset_growth_first_5000_spcx_cash_open_v55"
_PROFILE_FINGERPRINT = (
    "e918f81e55abb36ad207a1af69517dd4d8765b79eb972669195a6b180702d3c7"
)
_ASSETS = frozenset({"BTC", "HYPE", "xyz:SPCX"})
_SPCX_ROUTE = f"{HIP3_SPCX_CASH_OPEN_STRATEGY}|xyz:SPCX"
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE": [
        "long",
        "short",
    ],
    _SPCX_ROUTE: ["long", "short"],
}
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v55",
    schema_version="v55_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="spcx_cash_open_additive_live_research",
    maximum_margin_fraction=0.3,
    limitations=(
        "technical acceptance does not establish future profitability",
        "SPCX development evidence has 11 of 20 unresolved entry paths",
        "SPCX validation and holdout were not accessed",
        "a dynamic target cannot be venue-verified until an eligible entry occurs",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)


def build_v55_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    candidate_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 60.0,
) -> dict[str, object]:
    """Verify exact live v55 identity, additive routing, and exit contracts."""
    _require_config(config)
    candidate = _require_candidate(candidate_evidence)
    preflight = _require_flat_preflight(transition_preflight, config, _SPEC)
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    checks = _base_checks(
        checkpoint,
        audit,
        config,
        now_utc,
        maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds,
    )
    checks["direction_scope_identity"] = _direction_scope_check(
        checkpoint, _EXPECTED_SIDES
    )
    checks["bound_execution_plans"] = _bound_execution_plan_check(audit)
    checks["spcx_execution_contract"] = _spcx_execution_check(checkpoint, config)
    checks["spcx_readiness"] = _spcx_readiness_check(audit)
    reasons = _check_reasons(checks, "v55")
    return _report(checkpoint, checks, reasons, candidate, preflight)


def _base_checks(
    checkpoint: Record,
    audit: Record,
    config: MultiAssetLiveConfig,
    now_utc: datetime,
    checkpoint_age: float,
    pressure_age: float,
) -> dict[str, object]:
    return _shared_acceptance_checks(
        checkpoint,
        audit,
        config,
        now=_aware(now_utc),
        checkpoint_age=_positive(checkpoint_age, "checkpoint age"),
        pressure_age=_positive(pressure_age, "pressure age"),
    )


def _require_config(config: MultiAssetLiveConfig) -> None:
    spcx = next(
        (
            provider
            for provider in config.providers
            if provider.strategy_id == HIP3_SPCX_CASH_OPEN_STRATEGY
        ),
        None,
    )
    exact = (
        config.profile_id == _PROFILE_ID
        and config.profile_fingerprint == _PROFILE_FINGERPRINT
        and config.network == "mainnet"
        and config.margin_mode == "isolated"
        and config.maximum_positions == 10
        and set(config.symbols) == _ASSETS
        and len(config.executable_provider_symbols) == 4
        and len(config.executable_provider_directions) == 6
        and all(asset.leverage == 10.0 for asset in config.assets)
        and all(asset.margin_fraction == 0.1 for asset in config.assets)
        and all(asset.max_notional_usd == 5000.0 for asset in config.assets)
        and spcx is not None
        and _spcx_config_exact(spcx.execution)
    )
    if not exact:
        raise ValueError("post-start acceptance requires the exact v55 profile")


def _spcx_config_exact(execution: object) -> bool:
    return (
        getattr(execution, "entry_liquidity", None) == "taker_ioc"
        and getattr(execution, "stop_policy", None) == "fixed_bps"
        and getattr(execution, "stop_bps", None) == 80.0
        and getattr(execution, "target_policy", None) == "absolute_anchor"
        and getattr(execution, "maximum_hold_seconds", None) == 22500
        and getattr(execution, "provider_recipe_exit_policy", None) == "honor"
    )


def _require_candidate(evidence: Record) -> dict[str, object]:
    strategy = mapping(evidence.get("strategy_identity"), "SPCX strategy identity")
    execution = mapping(evidence.get("applied_execution"), "SPCX execution")
    disposition = mapping(evidence.get("research_disposition"), "SPCX disposition")
    status = disposition.get("status")
    exact = _candidate_header_exact(evidence, strategy, disposition)
    exact = exact and _candidate_execution_exact(execution)
    if not exact:
        raise ValueError("v55 SPCX candidate evidence identity is invalid")
    return {
        "symbol": "xyz:SPCX",
        "provider_id": strategy.get("provider_id"),
        "timeframe": "15m",
        "technical_disposition": status,
        "validation_accessed": False,
        "holdout_accessed": False,
    }


def _candidate_header_exact(
    evidence: Record, strategy: Record, disposition: Record
) -> bool:
    return (
        evidence.get("schema_version") == "hip3_cash_open_gap_reversal_development_v1"
        and evidence.get("symbol") == "xyz:SPCX"
        and evidence.get("report_only") is True
        and evidence.get("execution_authority") == "none"
        and evidence.get("validation_accessed") is False
        and evidence.get("holdout_accessed") is False
        and evidence.get("automatic_promotion") is False
        and evidence.get("live_roster_change") is False
        and disposition.get("live_change_proposed") is False
        and disposition.get("status") == "NOT_SUITABLE_TECHNICALLY_UNRESOLVED"
        and strategy.get("provider_id")
        == "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_research_v1"
        and strategy.get("timeframe") == "15m"
    )


def _candidate_execution_exact(execution: Record) -> bool:
    return (
        execution.get("leverage") == 10.0
        and execution.get("margin_fraction") == 0.1
        and execution.get("notional_usd") == 5000.0
        and execution.get("stop_bps") == 80.0
        and execution.get("maximum_hold_seconds") == 22500
        and execution.get("target_policy") == "prior_eligible_cash_session_close"
    )


def _spcx_execution_check(
    checkpoint: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    policies = mapping(
        generation.get("current_provider_exit_policies"), "provider exit policies"
    )
    policy = mapping(policies.get(HIP3_SPCX_CASH_OPEN_STRATEGY), "SPCX policy")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == HIP3_SPCX_CASH_OPEN_STRATEGY
    )
    exact = _spcx_config_exact(provider.execution) and (
        policy.get("maximum_hold_seconds") == 22500
        and policy.get("provider_recipe_exit_policy") == "honor"
    )
    return {
        "passed": exact,
        "reasons": [] if exact else ["spcx_execution_contract_mismatch"],
        "target_policy": provider.execution.target_policy,
        "maximum_hold_seconds": policy.get("maximum_hold_seconds"),
        "provider_recipe_exit_policy": policy.get("provider_recipe_exit_policy"),
    }


def _spcx_readiness_check(audit: Record) -> dict[str, object]:
    readiness = mapping(audit.get("readiness"), "audit readiness")
    routes = mapping(readiness.get("by_provider_symbol"), "provider readiness")
    row = mapping(routes.get(_SPCX_ROUTE), "SPCX readiness")
    metrics = mapping(row.get("latest_metrics"), "SPCX readiness metrics")
    exact = (
        nonnegative_int(row.get("count"), "SPCX evaluations") > 0
        and metrics.get("signal_source") == "hyperliquid_ws_trades"
        and metrics.get("gap_threshold_bps") == 20.0
        and nonnegative_int(metrics.get("public_trade_count"), "SPCX trade count") > 0
    )
    return {
        "passed": exact,
        "reasons": [] if exact else ["spcx_readiness_contract_missing"],
        "signal_source": metrics.get("signal_source"),
        "gap_threshold_bps": metrics.get("gap_threshold_bps"),
    }


def _report(
    checkpoint: Record,
    checks: Record,
    reasons: list[str],
    candidate: Record,
    preflight: Record,
) -> dict[str, object]:
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    return {
        "schema_version": _SPEC.schema_version,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_pause": False,
            "automatic_retuning": False,
            "automatic_strategy_changes": False,
        },
        "accepted": not reasons,
        "decision": "accepted" if not reasons else "rejected",
        "reasons": reasons,
        "run": dict(mapping(audit.get("run"), "checkpoint run")),
        "candidate_identity": dict(candidate),
        "preflight_identity": dict(preflight),
        "checks": dict(checks),
        "limitations": list(_SPEC.limitations),
    }
