"""Report-only technical acceptance for evidence-bound successor v52."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math

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

Record = Mapping[str, object]
_PROFILE_ID = "multi_asset_growth_first_5000_evidence_bound_successor_v52"
_PROFILE_FINGERPRINT = (
    "662d28b352cfc4f09e08c71ee67c8f044421483f2932539b09ea082b5e4f27f7"
)
_ASSETS = frozenset({"BTC", "HYPE"})
_ALIGNMENT_ROUTE = "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC": ["long"],
    _ALIGNMENT_ROUTE: ["long", "short"],
}
_SPEC = BtcSpecialistAcceptanceSpec(
    label="v52",
    schema_version="v52_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="evidence_bound_two_asset_successor",
    maximum_margin_fraction=0.2,
    limitations=(
        "technical acceptance does not establish future profitability",
        "the preflight must be regenerated at the final flat boundary",
        "HYPE aligned-side forward outcomes remain sparse",
        "sampled stop-wave stress is not a loss ceiling or probability forecast",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)


def build_v52_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    stress_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 60.0,
) -> dict[str, object]:
    """Verify exact live v52 identity, sizing, routing, and exit protection."""
    _require_config(config)
    stress = _require_stress_evidence(stress_evidence, config)
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
    checks["hype_alignment_readiness"] = _alignment_readiness_check(audit)
    checks["bound_execution_plans"] = _bound_execution_plan_check(audit)
    reasons = _check_reasons(checks, "v52")
    return _report(checkpoint, checks, reasons, stress, preflight)


def _require_config(config: MultiAssetLiveConfig) -> None:
    exact = (
        config.profile_id == _PROFILE_ID
        and config.profile_fingerprint == _PROFILE_FINGERPRINT
        and config.network == "mainnet"
        and config.margin_mode == "isolated"
        and config.maximum_positions == 10
        and set(config.symbols) == _ASSETS
        and len(config.providers) == 3
        and len(config.executable_provider_symbols) == 3
        and len(config.executable_provider_directions) == 4
        and all(asset.leverage == 10.0 for asset in config.assets)
        and all(asset.margin_fraction == 0.1 for asset in config.assets)
        and all(asset.max_notional_usd == 5000.0 for asset in config.assets)
    )
    if not exact:
        raise ValueError("post-start acceptance requires the exact v52 profile")


def _require_stress_evidence(
    evidence: Record,
    config: MultiAssetLiveConfig,
    *,
    label: str = "v52",
) -> dict[str, object]:
    contract = mapping(evidence.get("contract"), "v52 stress contract")
    sizing = mapping(evidence.get("sizing_plan"), "v52 sizing plan")
    by_asset = mapping(evidence.get("by_asset"), "v52 asset stress")
    actual = mapping(
        mapping(evidence.get("portfolio_stress"), "v52 portfolio stress").get(
            "configured_asset_roster"
        ),
        "v52 configured roster stress",
    )
    losses = [
        _asset_p99(by_asset.get(symbol), symbol, label) for symbol in sorted(_ASSETS)
    ]
    total = sum(losses)
    exact = _stress_header(evidence, contract, config) and _sizing_exact(sizing)
    exact = exact and set(by_asset) == _ASSETS and _actual_stress_exact(actual, total)
    if not exact:
        raise ValueError(f"{label} stress identity does not match config")
    return {
        "schema_version": 3,
        "profile_fingerprint": config.profile_fingerprint,
        "actual_position_count": 2,
        "actual_maximum_margin_fraction": 0.2,
        "p99_stop_wave_loss_usd": total,
        "p99_stop_wave_loss_pct_equity": total / 5000.0 * 100.0,
    }


def _stress_header(
    evidence: Record, contract: Record, config: MultiAssetLiveConfig
) -> bool:
    expected_contract = {
        "automatic_sizing_change": False,
        "balance_gate": False,
        "execution_authority": "none",
        "performance_gate": False,
        "profit_forecast": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    return (
        evidence.get("schema_version") == 3
        and evidence.get("mode") == "cohort_growth_sizing_stress_v3"
        and evidence.get("profile_id") == config.profile_id
        and evidence.get("profile_fingerprint") == config.profile_fingerprint
        and dict(contract) == expected_contract
    )


def _sizing_exact(sizing: Record) -> bool:
    expected = {
        "actual_roster_maximum_margin_fraction": 0.2,
        "configured_assets": 2,
        "leverage": 10.0,
        "margin_fraction_per_slot": 0.1,
        "maximum_positions": 10,
        "planned_margin_usd_per_slot": 500.0,
        "planned_notional_usd_per_slot": 5000.0,
        "target_equity_usd": 5000.0,
        "ten_slot_maximum_margin_fraction": 1.0,
        "unused_capacity_slots": 8,
    }
    return all(_same_number(sizing.get(key), value) for key, value in expected.items())


def _asset_p99(value: object, symbol: str, label: str) -> float:
    asset = mapping(value, f"{symbol} stress")
    p99 = mapping(asset.get("p99"), f"{symbol} p99 stress")
    loss = _finite_positive(p99.get("total_loss_usd"), f"{symbol} p99 loss")
    exact = (
        _same_number(asset.get("stop_bps"), 80.0)
        and _same_number(asset.get("visible_depth_complete_rate"), 1.0)
        and nonnegative_int(asset.get("visible_cost_sample_count"), "depth samples") > 0
        and _same_number(asset.get("current_profile_cap_usd"), 5000.0)
        and _same_number(asset.get("candidate_nonbinding_cap_usd"), 5000.0)
        and _same_number(asset.get("p99_total_loss_pct_equity"), loss / 50.0)
    )
    if not exact:
        raise ValueError(f"{label} stress identity does not match config")
    return loss


def _actual_stress_exact(actual: Record, total: float) -> bool:
    return (
        _same_number(actual.get("position_count"), 2.0)
        and _same_number(actual.get("isolated_margin_at_risk_usd"), 1000.0)
        and _same_number(actual.get("isolated_margin_at_risk_pct_equity"), 20.0)
        and _same_number(actual.get("p99_stop_wave_loss_usd"), total)
        and _same_number(actual.get("p99_stop_wave_loss_pct_equity"), total / 50.0)
    )


def _alignment_readiness_check(audit: Record) -> dict[str, object]:
    readiness = mapping(audit.get("readiness"), "audit readiness")
    routes = mapping(readiness.get("by_provider_symbol"), "provider readiness")
    row = mapping(routes.get(_ALIGNMENT_ROUTE), "HYPE alignment readiness")
    metrics = mapping(row.get("latest_metrics"), "HYPE alignment metrics")
    relation = metrics.get("breakout_side_relation")
    exact = (
        nonnegative_int(row.get("count"), "HYPE alignment evaluations") > 0
        and metrics.get("alignment_only") is True
        and metrics.get("breakout_side_alignment_required") is True
        and relation in {"aligned", "opposed", "unavailable"}
    )
    reasons = [] if exact else ["hype_alignment_readiness_contract_missing"]
    return {"passed": exact, "reasons": reasons, "latest_relation": relation}


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


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v52 acceptance clock must be timezone-aware")
    return value


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return result


def _finite_positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return result


def _same_number(value: object, expected: float) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and math.isclose(float(value), expected, rel_tol=1e-12, abs_tol=1e-12)
    )
