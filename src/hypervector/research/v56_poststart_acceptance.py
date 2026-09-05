"""Report-only technical acceptance for the incremental v56 BTC route."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_TUNED_SHORT_STRATEGY,
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
_PROFILE_ID = "multi_asset_growth_first_5000_btc_tuned_v2_increment_v56"
_PROFILE_FINGERPRINT = (
    "29a29ad11c9cc0613fd8fc93013758b8e093e96ff5f3698217b562b90f6e89c9"
)
_ASSETS = frozenset({"BTC", "HYPE", "xyz:SPCX"})
_TUNED_ROUTE = f"{HULK_TUNED_SHORT_STRATEGY}|BTC"
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    _TUNED_ROUTE: ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE": [
        "long",
        "short",
    ],
    "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX": [
        "long",
        "short",
    ],
}
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v56",
    schema_version="v56_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="btc_tuned_v2_incremental_live_research",
    maximum_margin_fraction=0.3,
    limitations=(
        "technical acceptance does not establish future profitability",
        "tuned-v2 is timing-sensitive and its latest exact signal lost",
        "HYPE cadence is unchanged by this increment",
        "one BTC position prevents simultaneous v2/v3 exposure",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)


def build_v56_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 60.0,
) -> dict[str, object]:
    """Verify exact v56 identity, incremental routing, and exit contracts."""
    _require_config(config)
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
    checks["tuned_v2_execution_contract"] = _tuned_execution_check(checkpoint, config)
    checks["tuned_v2_readiness"] = _tuned_readiness_check(audit)
    reasons = _check_reasons(checks, "v56")
    return _report(checkpoint, checks, reasons, preflight)


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
    tuned = next(
        (
            provider
            for provider in config.providers
            if provider.strategy_id == HULK_TUNED_SHORT_STRATEGY
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
        and len(config.executable_provider_directions) == 7
        and all(asset.leverage == 10.0 for asset in config.assets)
        and all(asset.margin_fraction == 0.1 for asset in config.assets)
        and all(asset.max_notional_usd == 5000.0 for asset in config.assets)
        and tuned is not None
        and tuned.priority == 19
        and _tuned_config_exact(tuned.execution)
    )
    if not exact:
        raise ValueError("post-start acceptance requires the exact v56 profile")


def _tuned_config_exact(execution: object) -> bool:
    return (
        getattr(execution, "entry_liquidity", None) == "taker_ioc"
        and getattr(execution, "stop_policy", None) == "structural_clamped_bps"
        and getattr(execution, "minimum_stop_bps", None) == 20.0
        and getattr(execution, "maximum_stop_bps", None) == 75.0
        and getattr(execution, "target_policy", None) == "reward_risk"
        and getattr(execution, "target_r_multiple", None) == 3.0
        and getattr(execution, "maximum_hold_seconds", None) == 86_400
    )


def _tuned_execution_check(
    checkpoint: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    policies = mapping(
        generation.get("current_provider_exit_policies"), "provider exit policies"
    )
    policy = mapping(policies.get(HULK_TUNED_SHORT_STRATEGY), "tuned-v2 policy")
    provider = next(
        row for row in config.providers if row.strategy_id == HULK_TUNED_SHORT_STRATEGY
    )
    exact = _tuned_config_exact(provider.execution) and (
        policy.get("maximum_hold_seconds") == 86_400
        and policy.get("provider_recipe_exit_policy") == "ignore"
    )
    return {
        "passed": exact,
        "reasons": [] if exact else ["tuned_v2_execution_contract_mismatch"],
        "target_r_multiple": provider.execution.target_r_multiple,
        "maximum_hold_seconds": policy.get("maximum_hold_seconds"),
    }


def _tuned_readiness_check(audit: Record) -> dict[str, object]:
    readiness = mapping(audit.get("readiness"), "audit readiness")
    routes = mapping(readiness.get("by_provider_symbol"), "provider readiness")
    row = mapping(routes.get(_TUNED_ROUTE), "tuned-v2 readiness")
    metrics = mapping(row.get("latest_metrics"), "tuned-v2 readiness metrics")
    exact = (
        nonnegative_int(row.get("count"), "tuned-v2 evaluations") > 0
        and metrics.get("entry_score_minimum") == 8
        and metrics.get("adx_usable") == 18.0
        and metrics.get("entry_contract") == "hulk_expansion_moderate_adx_v1"
    )
    return {
        "passed": exact,
        "reasons": [] if exact else ["tuned_v2_readiness_contract_missing"],
        "minimum_score": metrics.get("entry_score_minimum"),
        "adx_usable": metrics.get("adx_usable"),
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
            "automatic_pause": False,
            "automatic_retuning": False,
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
