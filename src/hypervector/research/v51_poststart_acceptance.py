"""Report-only technical acceptance for profit-protected growth profile v51."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.btc_specialist_friction_acceptance import (
    FrictionAcceptanceSpec,
)
from hypervector.research.growth_poststart_acceptance import (
    GrowthAcceptanceSpec,
    build_growth_poststart_acceptance,
)
from hypervector.research.v39_poststart_acceptance import (
    _acceptance_checks as _shared_acceptance_checks,
)
from hypervector.research.v50_poststart_acceptance import _ASSETS, _EXPECTED_SIDES
from hypervector.research.cohort_live_audit_values import mapping, mapping_list, text

Record = Mapping[str, object]
_PROFILE_ID = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
_PROFILE_FINGERPRINT = (
    "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908"
)
_FRICTION_SPEC = FrictionAcceptanceSpec(
    label="v51",
    schema_version="v51_growth_sizing_stress_v1",
    maximum_margin_fraction=0.6,
    explicit_candidate_depth=True,
    configured_leverage=10.0,
    variable_tiers="telemetry_only_not_execution_authorized",
    assets=_ASSETS,
    maximum_simultaneous_positions=6,
)
_SPEC = GrowthAcceptanceSpec(
    label="v51",
    schema_version="v51_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="six_asset_fresh15_v3_profit_protected_live_trial",
    maximum_margin_fraction=0.6,
    limitations=(
        "technical acceptance does not establish route profitability",
        "the preflight must be regenerated at the final flat boundary",
        "index profit-lock thresholds require prospective outcome validation",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
    assets=_ASSETS,
    provider_count=5,
    configured_leverage=10.0,
    pressure_age_seconds=15.0,
    friction=_FRICTION_SPEC,
)


def build_v51_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    friction_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 15.0,
) -> dict[str, object]:
    """Verify exact live v51 identity, route scope, and venue protection."""
    report = build_growth_poststart_acceptance(
        checkpoint,
        config,
        friction_evidence,
        transition_preflight,
        now_utc=now_utc,
        spec=_SPEC,
        shared_checks=_shared_acceptance_checks,
        maximum_checkpoint_age_seconds=maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds=maximum_pressure_age_seconds,
    )
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    check = _bound_execution_plan_check(audit)
    checks = dict(mapping(report.get("checks"), "v51 checks"))
    checks["bound_execution_plans"] = check
    reasons = list(report.get("reasons", ())) + list(check["reasons"])
    return report | {
        "accepted": not reasons,
        "decision": "accepted" if not reasons else "rejected",
        "reasons": reasons,
        "checks": checks,
    }


def _bound_execution_plan_check(audit: Record) -> dict[str, object]:
    health = mapping(audit.get("health", {}), "audit health")
    assets = mapping(health.get("assets", {}), "audit health assets")
    open_symbols = {
        symbol
        for symbol, raw in assets.items()
        if mapping(raw, f"{symbol} health").get("final_state") == "OPEN"
    }
    reflections = mapping(
        audit.get("open_trade_reflections", {"trades": []}),
        "open trade reflections",
    )
    bound = {
        text(row.get("symbol"), "open reflection symbol")
        for row in mapping_list(reflections.get("trades"), "open reflections")
        if mapping(row.get("exit_plan"), "open reflection exit plan").get("source")
        == "bound_execution_plan"
    }
    missing = sorted(open_symbols - bound)
    reasons = [
        f"open_lifecycle_missing_bound_execution_plan:{symbol}" for symbol in missing
    ]
    return {
        "passed": not reasons,
        "reasons": reasons,
        "open_positions": len(open_symbols),
        "bound_plans": len(open_symbols & bound),
    }
