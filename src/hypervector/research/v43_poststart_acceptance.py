"""Report-only technical acceptance for the exact BTC-specialist v43 profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.cohort_live_audit_values import mapping
from hypervector.research.v39_poststart_acceptance import (
    _acceptance_checks as _shared_acceptance_checks,
)

Record = Mapping[str, object]

_PROFILE_ID = "multi_asset_bidirectional_btc_specialists_candidate_v43"
_PROFILE_FINGERPRINT = (
    "3cb85383f63e346579bee66646d24c3808cbd49ec6d022f6ee51d0fa765340d7"
)
_EXPECTED_SIDES = {
    "hulk_expansion_short_robust_v3|BTC": ["short"],
    "liquidity_sweep_long_1h_stop60_v1|BTC": ["long"],
    "hype_breakout_compression_pullback_bidirectional_v1|HYPE": ["long", "short"],
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500": [
        "long",
        "short",
    ],
}


@dataclass(frozen=True)
class BtcSpecialistAcceptanceSpec:
    """Exact immutable identity expected by one BTC-specialist generation."""

    label: str
    schema_version: str
    profile_id: str
    profile_fingerprint: str
    expected_sides: Mapping[str, list[str]]
    evidence_state: str
    maximum_margin_fraction: float
    limitations: tuple[str, ...]


_V43_SPEC = BtcSpecialistAcceptanceSpec(
    label="v43",
    schema_version="v43_poststart_acceptance_v1",
    profile_id=_PROFILE_ID,
    profile_fingerprint=_PROFILE_FINGERPRINT,
    expected_sides=_EXPECTED_SIDES,
    evidence_state="two_distinct_forward_exact_n1_routes",
    maximum_margin_fraction=0.23203607689310038,
    limitations=(
        "technical acceptance does not establish route profitability",
        "each BTC specialist still has only one exact forward event",
        "the preflight must be regenerated at the final flat boundary",
        "this report cannot route, resize, pause, retune, or submit an order",
    ),
)


def build_v43_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    risk_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Verify one live v43 checkpoint against frozen transition evidence."""
    return build_btc_specialist_poststart_acceptance(
        checkpoint,
        config,
        risk_evidence,
        transition_preflight,
        now_utc=now_utc,
        spec=_V43_SPEC,
        maximum_checkpoint_age_seconds=maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds=maximum_pressure_age_seconds,
    )


def build_btc_specialist_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    risk_evidence: Record,
    transition_preflight: Record,
    *,
    now_utc: datetime,
    spec: BtcSpecialistAcceptanceSpec,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Verify one exact BTC-specialist runtime without execution authority."""
    _require_config(config, spec)
    evidence_identity = _require_risk_evidence(risk_evidence, config, spec)
    preflight_identity = _require_flat_preflight(transition_preflight, config, spec)
    now = _aware_utc(now_utc)
    checkpoint_age = _positive(maximum_checkpoint_age_seconds, "checkpoint age")
    pressure_age = _positive(maximum_pressure_age_seconds, "pressure age")
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    checks = _shared_acceptance_checks(
        checkpoint,
        audit,
        config,
        now=now,
        checkpoint_age=checkpoint_age,
        pressure_age=pressure_age,
    )
    checks["direction_scope_identity"] = _direction_scope_check(
        checkpoint, spec.expected_sides
    )
    reasons = _check_reasons(checks, spec.label)
    return {
        "schema_version": spec.schema_version,
        "contract": _contract(),
        "accepted": not reasons,
        "decision": "accepted" if not reasons else "rejected",
        "reasons": reasons,
        "run": dict(mapping(audit.get("run"), "checkpoint run")),
        "evidence_identity": evidence_identity,
        "preflight_identity": preflight_identity,
        "checks": checks,
        "limitations": list(spec.limitations),
    }


def _require_config(
    config: MultiAssetLiveConfig, spec: BtcSpecialistAcceptanceSpec
) -> None:
    exact = (
        config.profile_id == spec.profile_id
        and config.profile_fingerprint == spec.profile_fingerprint
        and config.network == "mainnet"
        and config.margin_mode == "isolated"
        and config.maximum_positions == 10
        and set(config.symbols) == {"BTC", "HYPE", "xyz:SP500"}
        and len(config.providers) == 4
        and len(config.executable_provider_symbols) == 4
        and len(config.executable_provider_directions) == 6
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


def _require_risk_evidence(
    evidence: Record,
    config: MultiAssetLiveConfig,
    spec: BtcSpecialistAcceptanceSpec,
) -> dict[str, object]:
    exact = (
        evidence.get("schema_version") == "btc_specialist_successor_risk_v1"
        and evidence.get("execution_authority") == "none"
        and evidence.get("profile_id") == config.profile_id
        and evidence.get("profile_fingerprint") == config.profile_fingerprint
        and evidence.get("repeatability_established") is False
        and evidence.get("evidence_state") == spec.evidence_state
    )
    if not exact:
        raise ValueError(f"{spec.label} risk identity does not match config")
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "repeatability_established": False,
        "evidence_state": evidence.get("evidence_state"),
    }


def _require_flat_preflight(
    preflight: Record,
    config: MultiAssetLiveConfig,
    spec: BtcSpecialistAcceptanceSpec,
) -> dict[str, object]:
    authority = mapping(preflight.get("authority"), "preflight authority")
    identity = mapping(preflight.get("identity"), "preflight identity")
    portfolio = mapping(preflight.get("portfolio"), "preflight portfolio")
    exact = (
        preflight.get("schema_version") == 1
        and authority.get("execution_authority") == "none"
        and identity.get("candidate_profile_id") == config.profile_id
        and identity.get("candidate_profile_fingerprint") == config.profile_fingerprint
        and portfolio.get("flat_no_orders") is True
        and portfolio.get("ledger_reconciled") is True
        and portfolio.get("sizing_technically_ready") is True
        and portfolio.get("technically_ready_for_profile_transition") is True
        and portfolio.get("open_positions") == 0
        and portfolio.get("open_orders") == 0
    )
    if not exact:
        raise ValueError(
            f"{spec.label} transition preflight must be flat and order-free"
        )
    return {
        "candidate_profile_id": config.profile_id,
        "candidate_profile_fingerprint": config.profile_fingerprint,
        "flat_no_orders": True,
        "ledger_reconciled": True,
    }


def _direction_scope_check(
    checkpoint: Record, expected_sides: Mapping[str, list[str]]
) -> dict[str, object]:
    generation = mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    raw = mapping(
        generation.get("current_provider_execution_directions"),
        "runtime provider execution directions",
    )
    observed = {str(key): _side_list(value, str(key)) for key, value in raw.items()}
    reasons = [] if observed == expected_sides else ["runtime_direction_scope_mismatch"]
    return {
        "passed": not reasons,
        "reasons": reasons,
        "provider_symbol_routes": len(observed),
        "directional_scopes": sum(len(sides) for sides in observed.values()),
    }


def _side_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        side not in {"long", "short"} for side in value
    ):
        raise ValueError(f"{label} direction scope must contain long/short values")
    sides = sorted(str(side) for side in value)
    if not sides or len(set(sides)) != len(sides):
        raise ValueError(f"{label} direction scope must be nonempty and unique")
    return sides


def _check_reasons(checks: Record, label: str) -> list[str]:
    reasons: list[str] = []
    for value in checks.values():
        check = mapping(value, f"{label} acceptance check")
        raw = check.get("reasons")
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise ValueError(f"{label} acceptance reasons must be strings")
        reasons.extend(raw)
    return reasons


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_pause": False,
        "automatic_retuning": False,
        "automatic_strategy_changes": False,
        "performance_gate": False,
    }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("acceptance clock must be timezone-aware")
    return value.astimezone(UTC)


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"maximum {label} must be positive and finite")
    return result
