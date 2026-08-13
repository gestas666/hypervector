"""Shared report-only acceptance for exact growth-profile generations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.btc_specialist_friction_acceptance import (
    FrictionAcceptanceSpec,
    require_friction_evidence,
)
from hypervector.research.cohort_live_audit_values import mapping
from hypervector.research.v43_poststart_acceptance import (
    BtcSpecialistAcceptanceSpec,
    _check_reasons,
    _direction_scope_check,
    _require_flat_preflight,
)

Record = Mapping[str, object]
SharedChecks = Callable[..., dict[str, object]]


@dataclass(frozen=True)
class GrowthAcceptanceSpec(BtcSpecialistAcceptanceSpec):
    """Exact runtime and friction identity for one growth generation."""

    assets: frozenset[str]
    provider_count: int
    configured_leverage: float
    pressure_age_seconds: float
    friction: FrictionAcceptanceSpec


def build_growth_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    friction_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    spec: GrowthAcceptanceSpec,
    shared_checks: SharedChecks,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float | None = None,
) -> dict[str, object]:
    """Verify exact identity and protection without granting authority."""
    _require_config(config, spec)
    checkpoint_age = _positive(maximum_checkpoint_age_seconds, "checkpoint age")
    pressure_age = _pressure_age(maximum_pressure_age_seconds, spec)
    friction = require_friction_evidence(friction_evidence, config, spec.friction)
    preflight = _require_flat_preflight(transition_preflight, config, spec)
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    checks = shared_checks(
        checkpoint,
        audit,
        config,
        now=_aware(now_utc, spec.label),
        checkpoint_age=checkpoint_age,
        pressure_age=pressure_age,
    )
    checks["direction_scope_identity"] = _direction_scope_check(
        checkpoint, spec.expected_sides
    )
    reasons = _check_reasons(checks, spec.label)
    return _report(checkpoint, checks, reasons, friction, preflight, spec)


def _require_config(config: MultiAssetLiveConfig, spec: GrowthAcceptanceSpec) -> None:
    route_count = len(spec.expected_sides)
    side_count = sum(len(sides) for sides in spec.expected_sides.values())
    exact = (
        config.profile_id == spec.profile_id
        and config.profile_fingerprint == spec.profile_fingerprint
        and config.network == "mainnet"
        and config.margin_mode == "isolated"
        and config.maximum_positions == 10
        and set(config.symbols) == spec.assets
        and len(config.providers) == spec.provider_count
        and len(config.executable_provider_symbols) == route_count
        and len(config.executable_provider_directions) == side_count
        and all(asset.leverage == spec.configured_leverage for asset in config.assets)
        and math.isclose(
            sum(asset.margin_fraction for asset in config.assets),
            spec.maximum_margin_fraction,
            abs_tol=1e-12,
        )
    )
    if not exact:
        raise ValueError(
            f"post-start acceptance requires the exact {spec.label} profile"
        )


def _report(
    checkpoint: Record,
    checks: Record,
    reasons: list[str],
    friction: Record,
    preflight: Record,
    spec: GrowthAcceptanceSpec,
) -> dict[str, object]:
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    return {
        "schema_version": spec.schema_version,
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
        "friction_identity": dict(friction),
        "preflight_identity": dict(preflight),
        "checks": dict(checks),
        "limitations": list(spec.limitations),
    }


def _pressure_age(value: float | None, spec: GrowthAcceptanceSpec) -> float:
    pressure = spec.pressure_age_seconds if value is None else value
    pressure = _positive(pressure, "pressure age")
    if not math.isclose(pressure, spec.pressure_age_seconds, abs_tol=1e-12):
        raise ValueError(
            f"{spec.label} pressure age must remain exactly "
            f"{spec.pressure_age_seconds:g} seconds"
        )
    return pressure


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} acceptance clock must be timezone-aware")
    return value


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return result
