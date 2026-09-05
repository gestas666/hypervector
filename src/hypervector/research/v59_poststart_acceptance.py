"""Report-only acceptance for the SP500 short-containment successor."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math

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
from hypervector.research.v58_poststart_acceptance import (
    _ASSET_SIZING,
    _EXPECTED_SIDES as _V58_EXPECTED_SIDES,
    _asset_sizing_check,
    _provider_exit_check,
    _require_stress_evidence as _require_inherited_stress_evidence,
)

Record = Mapping[str, object]
_PROFILE_ID = (
    "multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59"
)
_PROFILE_FINGERPRINT = (
    "c057882fdd0818831076685aa0fb0134b22889618f6c145ca8e1f9f33111ab78"
)
_V58_PROFILE_FINGERPRINT = (
    "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
)
_ACCOUNTING_START_VENUE_TIMESTAMP_MS = 1_787_164_729_837
_SP500_ROUTE = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
_SPCX_ROUTE = f"{HIP3_SPCX_CASH_OPEN_STRATEGY}|xyz:SPCX"
_SPCX_UNAVAILABLE_REASON = "cash_open_trade_bars_incomplete"
_EXPECTED_SIDES = {**_V58_EXPECTED_SIDES, _SP500_ROUTE: ["short"]}
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v59",
    schema_version="v59_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="sp500_long_contained_short_forward_research",
    maximum_margin_fraction=0.46,
    limitations=(
        "technical acceptance does not establish route profitability",
        "SP500 long remains observable but has no execution authority",
        "the V58 stress schema is inherited only because all risk fields are exact",
        "the preflight must be regenerated at the final flat boundary",
        "the stress report is a deterministic sensitivity, not a loss ceiling",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)


def build_v59_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    stress_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 15.0,
) -> dict[str, object]:
    """Verify exact V59 containment, topology, sizing, exits, and protection."""
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
    checks["sp500_long_authority_absent"] = _sp500_long_absent_check(checkpoint)
    checks["spcx_source_availability"] = _spcx_source_availability_check(audit)
    checks["asset_sizing_identity"] = _asset_sizing_check(checkpoint)
    checks["provider_exit_identity"] = _provider_exit_check(checkpoint, config)
    checks["bound_execution_plans"] = _bound_execution_plan_check(audit)
    checks["accounting_epoch_lineage"] = _accounting_epoch_lineage_check(audit)
    reasons = _check_reasons(checks, "v59")
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
        raise ValueError("V59 pressure age must remain exactly 15 seconds")
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
    reasons = [] if not missing and not extra else ["v59_provider_coverage_incomplete"]
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
    provider = next(
        (
            row
            for row in config.providers
            if f"{row.strategy_id}|xyz:SP500" == _SP500_ROUTE
        ),
        None,
    )
    exact = (
        config.profile_id == _PROFILE_ID
        and config.profile_fingerprint == _PROFILE_FINGERPRINT
        and config.network == "mainnet"
        and config.margin_mode == "isolated"
        and config.maximum_positions == 10
        and len(config.providers) == 9
        and len(config.executable_provider_symbols) == 10
        and len(config.executable_provider_directions) == 13
        and sizing == _ASSET_SIZING
        and provider is not None
        and provider.sides == {"long", "short"}
        and provider.executable_sides("xyz:SP500") == {"short"}
    )
    if not exact:
        raise ValueError("post-start acceptance requires the exact V59 profile")


def _require_stress_evidence(
    evidence: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    try:
        return _require_inherited_stress_evidence(evidence, config)
    except ValueError as exc:
        raise ValueError(
            "V59 stress evidence does not match the contained risk envelope"
        ) from exc


def _sp500_long_absent_check(checkpoint: Record) -> dict[str, object]:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    directions = mapping(
        generation.get("current_provider_execution_directions"),
        "provider execution directions",
    )
    absent = directions.get(_SP500_ROUTE) == ["short"]
    return {
        "passed": absent,
        "reasons": [] if absent else ["sp500_long_authority_present"],
    }


def _spcx_source_availability_check(audit: Record) -> dict[str, object]:
    readiness = mapping(audit.get("readiness"), "audit readiness")
    routes = mapping(readiness.get("by_provider_symbol"), "provider readiness")
    row = mapping(routes.get(_SPCX_ROUTE), "SPCX readiness")
    metrics = mapping(row.get("latest_metrics"), "SPCX readiness metrics")
    evaluations = nonnegative_int(row.get("count"), "SPCX evaluations")
    latest_reason = row.get("latest_reason")
    backend_reason = row.get("latest_backend_non_action_reason")
    raw_blockers = row.get("latest_blockers", [])
    blockers = raw_blockers if isinstance(raw_blockers, list) else []
    signal_source = metrics.get("signal_source")
    trade_count = metrics.get("public_trade_count")
    trade_count_valid = (
        isinstance(trade_count, int)
        and not isinstance(trade_count, bool)
        and trade_count > 0
    )
    unavailable = _SPCX_UNAVAILABLE_REASON in {
        latest_reason,
        backend_reason,
        *blockers,
    }
    exact = (
        evaluations > 0
        and not unavailable
        and metrics.get("technical_availability") != "unavailable"
        and signal_source == "hyperliquid_ws_trades"
        and trade_count_valid
    )
    reason = "spcx_cash_open_source_unavailable"
    return {
        "passed": exact,
        "reasons": [] if exact else [reason],
        "evaluations": evaluations,
        "latest_reason": latest_reason,
        "latest_backend_non_action_reason": backend_reason,
        "signal_source": signal_source,
        "public_trade_count": trade_count,
    }


def _accounting_epoch_lineage_check(audit: Record) -> dict[str, object]:
    archive = audit.get("portfolio_archive")
    epoch = archive.get("accounting_epoch") if isinstance(archive, Mapping) else None
    expected_profiles = [_V58_PROFILE_FINGERPRINT, _PROFILE_FINGERPRINT]
    exact = isinstance(epoch, Mapping) and all(
        (
            epoch.get("profile_fingerprint") == _PROFILE_FINGERPRINT,
            epoch.get("start_venue_timestamp_ms")
            == _ACCOUNTING_START_VENUE_TIMESTAMP_MS,
            epoch.get("included_profile_fingerprints") == expected_profiles,
        )
    )
    reason = "v59_accounting_epoch_lineage_mismatch"
    return {
        "passed": exact,
        "reasons": [] if exact else [reason],
        "expected_current_profile_fingerprint": _PROFILE_FINGERPRINT,
        "expected_start_venue_timestamp_ms": _ACCOUNTING_START_VENUE_TIMESTAMP_MS,
        "expected_included_profile_fingerprints": expected_profiles,
        "observed": dict(epoch) if isinstance(epoch, Mapping) else None,
    }


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
