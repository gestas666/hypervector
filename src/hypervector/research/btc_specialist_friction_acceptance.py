"""Exact friction-evidence contracts for BTC-specialist generations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.cohort_live_audit_values import mapping

Record = Mapping[str, object]


@dataclass(frozen=True)
class FrictionAcceptanceSpec:
    """Frozen identity and sizing shape for one technical acceptance report."""

    label: str
    schema_version: str
    maximum_margin_fraction: float
    explicit_candidate_depth: bool = False
    configured_leverage: float | None = None
    variable_tiers: str | None = None
    assets: frozenset[str] | None = None
    maximum_simultaneous_positions: int = 3


def require_friction_evidence(
    evidence: Record,
    config: MultiAssetLiveConfig,
    spec: FrictionAcceptanceSpec,
) -> dict[str, object]:
    """Require exact profile, scenarios, depth, and sizing authority."""
    contract = mapping(evidence.get("contract"), f"{spec.label} friction contract")
    scenarios = _scenarios(evidence.get("scenarios"), spec.label)
    exact = (
        evidence.get("schema_version") == spec.schema_version
        and evidence.get("profile_id") == config.profile_id
        and evidence.get("profile_fingerprint") == config.profile_fingerprint
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and [row["account_value_usd"] for row in scenarios] == [500.0, 5000.0]
        and all(_exact_scenario(row, spec) for row in scenarios)
        and _optional_growth_contract(evidence, spec)
    )
    if not exact:
        raise ValueError(f"{spec.label} friction identity does not match config")
    return _identity_payload(config, spec)


def _optional_growth_contract(evidence: Record, spec: FrictionAcceptanceSpec) -> bool:
    if not spec.explicit_candidate_depth:
        return True
    depth = mapping(evidence.get("visible_depth_contract"), "visible-depth contract")
    sizing = mapping(evidence.get("sizing_policy"), "sizing policy")
    p99 = mapping(depth.get("p99_bps_by_asset"), "visible-depth p99")
    return (
        depth.get("source") == "explicit_candidate_notional_override"
        and set(p99) == _expected_assets(spec)
        and all(_nonnegative(value) for value in p99.values())
        and sizing.get("configured_leverage") == spec.configured_leverage
        and sizing.get("variable_tiers") == spec.variable_tiers
        and sizing.get("readiness_is_win_probability") is False
    )


def _scenarios(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} friction evidence requires two scenarios")
    return [mapping(row, f"{label} friction scenario") for row in value]


def _exact_scenario(row: Record, spec: FrictionAcceptanceSpec) -> bool:
    slots = mapping(row.get("asset_slots"), "friction asset slots")
    observed_margin = row.get("route_aware_maximum_margin_fraction")
    return (
        row.get("maximum_simultaneous_positions") == spec.maximum_simultaneous_positions
        and row.get("account_position_capacity") == 10
        and _finite(observed_margin)
        and math.isclose(
            float(observed_margin), spec.maximum_margin_fraction, abs_tol=1e-12
        )
        and set(slots) == _expected_assets(spec)
    )


def _expected_assets(spec: FrictionAcceptanceSpec) -> frozenset[str]:
    return spec.assets or frozenset({"BTC", "HYPE", "xyz:SP500"})


def _identity_payload(
    config: MultiAssetLiveConfig, spec: FrictionAcceptanceSpec
) -> dict[str, object]:
    return {
        "schema_version": spec.schema_version,
        "profile_fingerprint": config.profile_fingerprint,
        "scenario_accounts_usd": [500.0, 5000.0],
        "maximum_simultaneous_positions": spec.maximum_simultaneous_positions,
        "maximum_margin_fraction": spec.maximum_margin_fraction,
        "configured_leverage": spec.configured_leverage,
        "variable_tiers": spec.variable_tiers,
    }


def _nonnegative(value: object) -> bool:
    return _finite(value) and float(value) >= 0.0


def _finite(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
