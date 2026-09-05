"""Report-only technical acceptance for the v53 HYPE freshness repair."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
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
from hypervector.research.v51_poststart_acceptance import (
    _bound_execution_plan_check,
)
from hypervector.research.v52_poststart_acceptance import (
    _alignment_readiness_check,
    _aware,
    _positive,
    _require_stress_evidence,
)

Record = Mapping[str, object]
_PROFILE_ID = "multi_asset_growth_first_5000_hype_freshness_repair_v53"
_PROFILE_FINGERPRINT = (
    "f6378e473088b962724176f1b4aaf0857d4e2a6c3bf0103c2d1794d6bfd46a82"
)
_ASSETS = frozenset({"BTC", "HYPE"})
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    f"{HYPE_COMPRESSION_ALIGNMENT_STRATEGY}|HYPE": ["long", "short"],
}
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v53",
    schema_version="v53_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="hype_maximum_hold_evidence_freshness_repair",
    maximum_margin_fraction=0.2,
    limitations=(
        "technical acceptance does not establish future profitability",
        "the 60-second evidence bound applies only at HYPE's soft deadline",
        "sampled stop-wave stress is not a loss ceiling or probability forecast",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)


def build_v53_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    stress_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 60.0,
) -> dict[str, object]:
    """Verify exact live v53 identity, routing, and repaired exit evidence."""
    _require_config(config)
    stress = _require_stress_evidence(stress_evidence, config, label="v53")
    preflight = _require_flat_preflight(transition_preflight, config, _SPEC)
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    checks = _acceptance_checks(
        checkpoint,
        audit,
        config,
        now_utc,
        maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds,
    )
    checks["maximum_hold_evidence_freshness"] = _freshness_check(checkpoint, config)
    reasons = _check_reasons(checks, "v53")
    return _report(checkpoint, checks, reasons, stress, preflight)


def _acceptance_checks(
    checkpoint: Record,
    audit: Record,
    config: MultiAssetLiveConfig,
    now_utc: datetime,
    checkpoint_age: float,
    pressure_age: float,
) -> dict[str, object]:
    checks = _shared_acceptance_checks(
        checkpoint,
        audit,
        config,
        now=_aware(now_utc),
        checkpoint_age=_positive(checkpoint_age, "checkpoint age"),
        pressure_age=_positive(pressure_age, "pressure age"),
    )
    checks["direction_scope_identity"] = _direction_scope_check(
        checkpoint, _EXPECTED_SIDES
    )
    checks["hype_alignment_readiness"] = _alignment_readiness_check(audit)
    checks["bound_execution_plans"] = _bound_execution_plan_check(audit)
    return checks


def _require_config(config: MultiAssetLiveConfig) -> None:
    hype = next(
        (
            row
            for row in config.providers
            if row.strategy_id == HYPE_COMPRESSION_ALIGNMENT_STRATEGY
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
        and len(config.executable_provider_symbols) == 3
        and len(config.executable_provider_directions) == 4
        and hype is not None
        and hype.execution.maximum_hold_evidence_maximum_age_seconds == 60
    )
    if not exact:
        raise ValueError("post-start acceptance requires the exact v53 profile")


def _freshness_check(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
) -> dict[str, object]:
    generation = checkpoint.get("configuration_generation")
    policies = (
        generation.get("current_provider_exit_policies")
        if isinstance(generation, Mapping)
        else None
    )
    row = (
        policies.get(HYPE_COMPRESSION_ALIGNMENT_STRATEGY)
        if isinstance(policies, Mapping)
        else None
    )
    observed = (
        row.get("maximum_hold_evidence_maximum_age_seconds")
        if isinstance(row, Mapping)
        else None
    )
    configured = next(
        provider.execution.maximum_hold_evidence_maximum_age_seconds
        for provider in config.providers
        if provider.strategy_id == HYPE_COMPRESSION_ALIGNMENT_STRATEGY
    )
    passed = observed == configured == 60
    return {
        "passed": passed,
        "reasons": [] if passed else ["maximum_hold_evidence_freshness_mismatch"],
        "maximum_age_seconds": observed,
    }


def _report(
    checkpoint: Record,
    checks: Record,
    reasons: list[str],
    stress: Record,
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
        "stress_identity": dict(stress),
        "preflight_identity": dict(preflight),
        "checks": dict(checks),
        "limitations": list(_SPEC.limitations),
    }
