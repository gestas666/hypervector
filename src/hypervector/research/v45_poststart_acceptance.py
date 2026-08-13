"""Report-only technical acceptance for the growth-sized v45 profile."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.btc_specialist_friction_acceptance import (
    FrictionAcceptanceSpec,
    require_friction_evidence,
)
from hypervector.research.cohort_live_audit_values import mapping, nonnegative_int
from hypervector.research.v43_poststart_acceptance import (
    BtcSpecialistAcceptanceSpec,
    build_btc_specialist_poststart_acceptance,
)

Record = Mapping[str, object]
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    "hype_breakout_compression_pullback_bidirectional_v1|HYPE": ["long", "short"],
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500": [
        "long",
        "short",
    ],
}
_MARGIN = 0.30666666666666664
V45_ROUTE_NATIVE_SIZING_FEATURES = {
    "hulk_expansion_short_robust_v3|BTC": (
        "adx",
        "ema_trend",
        "entry_score",
        "money_flow_direction",
        "squeeze_on",
        "squeeze_release",
        "supertrend_direction",
        "volume_ratio",
    ),
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": (
        "clearance_bps",
        "close_above_ema55",
        "ema55",
        "reclaim_close",
        "sweep_low",
        "volume_multiple",
    ),
    "hype_breakout_compression_pullback_bidirectional_v1|HYPE": (
        "authoritative_5m_bbwp_percentile",
        "breakout_clearance_20m_bps",
        "breakout_volume_ratio",
        "current_bbwp_percentile",
        "directional_bar_body_bps",
        "prior_bbwp_below25_count_15m",
        "prior_bbwp_min_15m",
    ),
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500": (
        "breakout_level",
        "directional_breakout_distance_bps",
        "ema_fast",
        "ema_slow",
        "imbalance_10",
        "pressure_age_seconds",
        "pressure_status",
    ),
}
_SIZING_FEATURES = V45_ROUTE_NATIVE_SIZING_FEATURES
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v45",
    schema_version="v45_poststart_acceptance_v2",
    profile_id="multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45",
    profile_fingerprint=(
        "e1b46ba749a46cc2966f0b4629bfd487c3d6dfe1a29de745d9f9eb7c8e22c6f5"
    ),
    expected_sides=_EXPECTED_SIDES,
    evidence_state="short_n1_long_taker_path_unresolved",
    maximum_margin_fraction=_MARGIN,
    limitations=(
        "technical acceptance does not establish route profitability",
        "variable exposure tiers remain telemetry-only",
        "the preflight must be regenerated at the final flat boundary",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)
_FRICTION_SPEC = FrictionAcceptanceSpec(
    label="v45",
    schema_version="v45_portfolio_friction_stress_v1",
    maximum_margin_fraction=_MARGIN,
    explicit_candidate_depth=True,
    configured_leverage=5.0,
    variable_tiers="telemetry_only_not_execution_authorized",
)


def build_v45_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    risk_evidence: Record,
    friction_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Verify live v45 identity, sizing, and technical evidence."""
    friction_identity = require_friction_evidence(
        friction_evidence, config, _FRICTION_SPEC
    )
    report = build_btc_specialist_poststart_acceptance(
        checkpoint,
        config,
        risk_evidence,
        transition_preflight,
        now_utc=now_utc,
        spec=_SPEC,
        maximum_checkpoint_age_seconds=maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds=maximum_pressure_age_seconds,
    )
    sizing_check = _sizing_feature_check(checkpoint)
    checks = dict(mapping(report.get("checks"), "v45 acceptance checks"))
    checks["route_native_sizing_features"] = sizing_check
    reasons = list(report["reasons"]) + list(sizing_check["reasons"])
    report["checks"] = checks
    report["reasons"] = reasons
    report["accepted"] = not reasons
    report["decision"] = "accepted" if not reasons else "rejected"
    report["friction_identity"] = friction_identity
    return report


def _sizing_feature_check(checkpoint: Record) -> dict[str, object]:
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    outcomes = mapping(audit.get("signal_outcomes"), "signal outcomes")
    by_route = mapping(outcomes.get("by_provider_symbol"), "provider outcomes")
    reasons: list[str] = []
    verified: dict[str, int] = {}
    for route, required in _SIZING_FEATURES.items():
        raw = by_route.get(route)
        if not isinstance(raw, Mapping):
            reasons.append(f"sizing_route_missing:{route}")
            continue
        evaluations = nonnegative_int(raw.get("evaluations"), f"{route} evaluations")
        diagnostics = mapping(raw.get("metric_diagnostics"), f"{route} diagnostics")
        coverage = mapping(diagnostics.get("coverage"), f"{route} metric coverage")
        metrics = mapping(diagnostics.get("metrics"), f"{route} metrics")
        if evaluations == 0:
            reasons.append(f"sizing_route_not_evaluated:{route}")
        if nonnegative_int(coverage.get("evaluations_without_metrics"), route):
            reasons.append(f"sizing_route_metrics_missing:{route}")
        verified[route] = _verify_route_features(
            route, required, metrics, evaluations, reasons
        )
    return {
        "passed": not reasons,
        "reasons": reasons,
        "execution_authority": "none",
        "sizing_tiers": [0.75, 1.0, 1.25],
        "verified_features_by_route": verified,
    }


def _verify_route_features(
    route: str,
    required: tuple[str, ...],
    metrics: Record,
    evaluations: int,
    reasons: list[str],
) -> int:
    verified = 0
    for name in required:
        raw = metrics.get(name)
        if not isinstance(raw, Mapping):
            reasons.append(f"sizing_feature_missing:{route}:{name}")
            continue
        observed = nonnegative_int(raw.get("observations"), f"{route} {name} observed")
        missing = nonnegative_int(
            raw.get("missing_evaluations"), f"{route} {name} missing"
        )
        if observed + missing != evaluations:
            reasons.append(f"sizing_feature_accounting_mismatch:{route}:{name}")
        elif observed == 0:
            reasons.append(f"sizing_feature_never_observed:{route}:{name}")
        else:
            verified += 1
    return verified
