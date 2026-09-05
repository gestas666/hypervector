"""Report-only technical acceptance for SPCX short-side containment."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.live.hip3_cash_open_gap_provider import (
    HIP3_SPCX_CASH_OPEN_STRATEGY,
)
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.cohort_live_audit_values import mapping
from hypervector.research.v39_poststart_acceptance import (
    _acceptance_checks as _shared_acceptance_checks,
)
from hypervector.research.v43_poststart_acceptance import (
    BtcSpecialistAcceptanceSpec,
    _check_reasons,
    _direction_scope_check,
    _require_flat_preflight,
)
from hypervector.research.v52_poststart_acceptance import _aware, _positive

Record = Mapping[str, object]
_PROFILE_ID = "multi_asset_growth_first_5000_spcx_short_containment_v57"
_PROFILE_FINGERPRINT = (
    "724c259bd94be60d80ffc2e6b9a760412b9729ab1f8fea403e61d266f0d9cb8d"
)
_ASSETS = frozenset({"BTC", "HYPE", "xyz:SPCX"})
_SPCX_ROUTE = f"{HIP3_SPCX_CASH_OPEN_STRATEGY}|xyz:SPCX"
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "hulk_expansion_short_tuned_v2|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE": [
        "long",
        "short",
    ],
    _SPCX_ROUTE: ["short"],
}
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v57",
    schema_version="v57_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="spcx_long_contained_short_forward_research",
    maximum_margin_fraction=0.3,
    limitations=(
        "technical acceptance does not establish future profitability",
        "SPCX short has no exact resolved v57 lifecycle yet",
        "SPCX long remains observable but has no execution authority",
        "this report cannot route, resize, retune, or submit an order",
    ),
)


def build_v57_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 60.0,
) -> dict[str, object]:
    """Verify exact v57 identity, SPCX containment, and preserved exits."""
    _require_config(config)
    preflight = _require_flat_preflight(transition_preflight, config, _SPEC)
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    checks = _shared_acceptance_checks(
        checkpoint,
        audit,
        config,
        now=_aware(now_utc),
        checkpoint_age=_positive(maximum_checkpoint_age_seconds, "checkpoint age"),
        pressure_age=_positive(maximum_pressure_age_seconds, "pressure age"),
    )
    checks["direction_scope_identity"] = _direction_scope_check(
        checkpoint, _EXPECTED_SIDES
    )
    checks["spcx_short_exit_contract"] = _spcx_exit_check(checkpoint, config)
    checks["spcx_long_authority_absent"] = _long_absent_check(checkpoint)
    reasons = _check_reasons(checks, "v57")
    return _report(checkpoint, checks, reasons, preflight)


def _require_config(config: MultiAssetLiveConfig) -> None:
    provider = next(
        (
            row
            for row in config.providers
            if row.strategy_id == HIP3_SPCX_CASH_OPEN_STRATEGY
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
        and len(config.executable_provider_symbols) == 5
        and len(config.executable_provider_directions) == 6
        and provider is not None
        and provider.executable_sides("xyz:SPCX") == {"short"}
        and _spcx_execution_exact(provider.execution)
    )
    if not exact:
        raise ValueError("post-start acceptance requires the exact v57 profile")


def _spcx_execution_exact(execution: object) -> bool:
    return (
        getattr(execution, "entry_liquidity", None) == "taker_ioc"
        and getattr(execution, "stop_policy", None) == "fixed_bps"
        and getattr(execution, "stop_bps", None) == 80.0
        and getattr(execution, "target_policy", None) == "absolute_anchor"
        and getattr(execution, "maximum_hold_seconds", None) == 22_500
        and getattr(execution, "provider_recipe_exit_policy", None) == "honor"
    )


def _spcx_exit_check(
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
    exact = _spcx_execution_exact(provider.execution) and (
        policy.get("maximum_hold_seconds") == 22_500
        and policy.get("provider_recipe_exit_policy") == "honor"
    )
    return {
        "passed": exact,
        "reasons": [] if exact else ["spcx_short_exit_contract_mismatch"],
    }


def _long_absent_check(checkpoint: Record) -> dict[str, object]:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    directions = mapping(
        generation.get("current_provider_execution_directions"),
        "provider execution directions",
    )
    absent = directions.get(_SPCX_ROUTE) == ["short"]
    return {
        "passed": absent,
        "reasons": [] if absent else ["spcx_long_authority_present"],
    }


def _report(
    checkpoint: Record,
    checks: Record,
    reasons: list[str],
    preflight: Record,
) -> dict[str, object]:
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    return {
        "schema_version": _SPEC.schema_version,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_strategy_changes": False,
        },
        "accepted": not reasons,
        "decision": "accepted" if not reasons else "rejected",
        "reasons": reasons,
        "run": dict(mapping(audit.get("run"), "checkpoint run")),
        "preflight_identity": dict(preflight),
        "checks": dict(checks),
        "limitations": list(_SPEC.limitations),
    }
