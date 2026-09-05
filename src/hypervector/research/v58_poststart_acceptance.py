"""Report-only technical acceptance for the exact eight-asset V58 profile."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.cohort_configuration_exit_policy import (
    provider_exit_expectation,
    provider_exit_policy_evidence,
)
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
_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_PROFILE_FINGERPRINT = (
    "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
)
_ASSET_SIZING = {
    "BTC": {"leverage": 10.0, "margin_fraction": 0.1, "max_notional_usd": 5000.0},
    "ETH": {"leverage": 5.0, "margin_fraction": 0.03, "max_notional_usd": 750.0},
    "SOL": {"leverage": 5.0, "margin_fraction": 0.03, "max_notional_usd": 750.0},
    "HYPE": {"leverage": 10.0, "margin_fraction": 0.1, "max_notional_usd": 5000.0},
    "xyz:SP500": {
        "leverage": 5.0,
        "margin_fraction": 0.07,
        "max_notional_usd": 1750.0,
    },
    "xyz:SPCX": {
        "leverage": 5.0,
        "margin_fraction": 0.07,
        "max_notional_usd": 1750.0,
    },
    "xyz:SNDK": {
        "leverage": 5.0,
        "margin_fraction": 0.03,
        "max_notional_usd": 750.0,
    },
    "xyz:BRENTOIL": {
        "leverage": 5.0,
        "margin_fraction": 0.03,
        "max_notional_usd": 750.0,
    },
}
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "hulk_expansion_short_tuned_v2|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH": ["long", "short"],
    "hulk_expansion_bidirectional_tuned_v2|SOL": ["short"],
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE": ["long", "short"],
    "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500": [
        "long",
        "short",
    ],
    "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX": ["short"],
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK": [
        "short"
    ],
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL": [
        "long",
        "short",
    ],
}
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v58",
    schema_version="v58_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="eight_asset_incremental_live_research",
    maximum_margin_fraction=0.46,
    limitations=(
        "technical acceptance does not establish route profitability",
        "the preflight must be regenerated at the final flat boundary",
        "the stress report is a deterministic sensitivity, not a loss ceiling",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)


def build_v58_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    stress_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 15.0,
) -> dict[str, object]:
    """Verify exact V58 identity, topology, sizing, exits, and protection."""
    _require_config(config)
    stress = _require_stress_evidence(stress_evidence, config)
    preflight = _require_flat_preflight(transition_preflight, config, _SPEC)
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    coverage = _provider_coverage_check(audit)
    checks = (
        _base_checks(
            checkpoint,
            audit,
            config,
            now_utc,
            maximum_checkpoint_age_seconds,
            maximum_pressure_age_seconds,
        )
        if coverage["passed"]
        else {}
    )
    checks["poststart_provider_coverage"] = coverage
    checks["direction_scope_identity"] = _direction_scope_check(
        checkpoint, _EXPECTED_SIDES
    )
    checks["asset_sizing_identity"] = _asset_sizing_check(checkpoint)
    checks["provider_exit_identity"] = _provider_exit_check(checkpoint, config)
    checks["bound_execution_plans"] = _bound_execution_plan_check(audit)
    reasons = _check_reasons(checks, "v58")
    return _report(checkpoint, checks, reasons, preflight, stress)


def _base_checks(
    checkpoint: Record,
    audit: Record,
    config: MultiAssetLiveConfig,
    now_utc: datetime,
    checkpoint_age: float,
    pressure_age: float,
) -> dict[str, object]:
    age = _positive(pressure_age, "pressure age")
    if not math.isclose(age, 15.0, abs_tol=1e-12):
        raise ValueError("V58 pressure age must remain exactly 15 seconds")
    return _shared_acceptance_checks(
        checkpoint,
        audit,
        config,
        now=_aware(now_utc),
        checkpoint_age=_positive(checkpoint_age, "checkpoint age"),
        pressure_age=age,
    )


def _provider_coverage_check(audit: Record) -> dict[str, object]:
    readiness = mapping(audit.get("readiness"), "audit readiness")
    routes = mapping(readiness.get("by_provider_symbol"), "provider readiness")
    observed = set(routes)
    evaluated = {
        route
        for route, value in routes.items()
        if nonnegative_int(
            mapping(value, f"{route} readiness").get("count"),
            f"{route} evaluations",
        )
        > 0
    }
    expected = set(_EXPECTED_SIDES)
    missing = sorted(expected - evaluated)
    extra = sorted(observed - expected)
    reasons = [] if not missing and not extra else ["v58_provider_coverage_incomplete"]
    return {
        "passed": not reasons,
        "reasons": reasons,
        "observed_routes": len(observed),
        "evaluated_routes": len(evaluated),
        "missing_routes": missing,
        "unexpected_routes": extra,
    }


def _require_config(config: MultiAssetLiveConfig) -> None:
    sizing = {
        asset.symbol: {
            "leverage": asset.leverage,
            "margin_fraction": asset.margin_fraction,
            "max_notional_usd": asset.max_notional_usd,
        }
        for asset in config.assets
    }
    exact = (
        config.profile_id == _PROFILE_ID
        and config.profile_fingerprint == _PROFILE_FINGERPRINT
        and config.network == "mainnet"
        and config.margin_mode == "isolated"
        and config.maximum_positions == 10
        and len(config.providers) == 9
        and len(config.executable_provider_symbols) == 10
        and len(config.executable_provider_directions) == 14
        and sizing == _ASSET_SIZING
    )
    if not exact:
        raise ValueError("post-start acceptance requires the exact V58 profile")


def _require_stress_evidence(
    evidence: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    contract = mapping(evidence.get("contract"), "V58 stress contract")
    envelope = mapping(evidence.get("v58_preflight_evidence"), "V58 stress envelope")
    scenarios = evidence.get("scenarios")
    scenario = (
        scenarios[0] if isinstance(scenarios, list) and len(scenarios) == 1 else {}
    )
    exact = (
        evidence.get("schema_version") == "v58_eight_asset_growth_stress_v1"
        and evidence.get("profile_id") == config.profile_id
        and evidence.get("profile_fingerprint") == config.profile_fingerprint
        and _stress_contract_exact(contract)
        and _stress_envelope_exact(envelope)
        and _stress_scenario_exact(scenario)
    )
    if not exact:
        raise ValueError("V58 stress evidence does not match the live envelope")
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "maximum_margin_fraction": 0.46,
        "maximum_simultaneous_positions": 8,
    }


def _stress_contract_exact(contract: Record) -> bool:
    return (
        contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("performance_gate") is False
        and contract.get("runtime_strategy_changed") is False
        and contract.get("automatic_sizing_change") is False
    )


def _stress_envelope_exact(envelope: Record) -> bool:
    notionals = {
        symbol: row["max_notional_usd"] for symbol, row in _ASSET_SIZING.items()
    }
    return (
        envelope.get("configured_assets") == 8
        and envelope.get("maximum_positions") == 10
        and envelope.get("maximum_configured_margin_fraction") == 0.46
        and envelope.get("sizing_reference_equity_usd") == 5000.0
        and envelope.get("planned_notionals_usd") == notionals
        and envelope.get("fee_stress_conservative_for_current_inputs") is True
    )


def _stress_scenario_exact(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return (
        value.get("account_position_capacity") == 10
        and value.get("account_value_usd") == 5000.0
        and value.get("maximum_simultaneous_positions") == 8
        and value.get("route_aware_maximum_margin_fraction") == 0.46
        and set(mapping(value.get("asset_slots"), "V58 stress asset slots"))
        == set(_ASSET_SIZING)
    )


def _asset_sizing_check(checkpoint: Record) -> dict[str, object]:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    raw = mapping(generation.get("current_asset_sizing"), "runtime asset sizing")
    observed = {
        symbol: dict(mapping(value, f"{symbol} runtime sizing"))
        for symbol, value in raw.items()
    }
    reasons = [] if observed == _ASSET_SIZING else ["runtime_asset_sizing_mismatch"]
    return {"passed": not reasons, "reasons": reasons, "assets": len(observed)}


def _provider_exit_check(
    checkpoint: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    observed = mapping(
        generation.get("current_provider_exit_policies"), "runtime exit policies"
    )
    expected = provider_exit_policy_evidence(provider_exit_expectation(config))
    reasons = [] if observed == expected else ["runtime_provider_exit_mismatch"]
    return {"passed": not reasons, "reasons": reasons, "providers": len(observed)}


def _report(
    checkpoint: Record,
    checks: Record,
    reasons: list[str],
    preflight: Record,
    stress: Record,
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
            "performance_gate": False,
        },
        "accepted": not reasons,
        "decision": "accepted" if not reasons else "rejected",
        "reasons": reasons,
        "run": dict(mapping(audit.get("run"), "checkpoint run")),
        "stress_identity": dict(stress),
        "preflight_identity": dict(preflight),
        "checks": dict(checks),
        "limitations": list(_SPEC.limitations),
    }
