"""Report-only technical acceptance for the exact $5K v41 profile."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.cohort_live_audit_values import mapping
from hypervector.research.v39_poststart_acceptance import (
    _acceptance_checks as _shared_acceptance_checks,
)

Record = Mapping[str, object]

_PROFILE_ID = (
    "multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41"
)
_PROFILE_FINGERPRINT = (
    "c940b2ef8ec444b880910eacaf600d5927654e280941f8aaf0bec781f1739de7"
)


def build_v41_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    readiness: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Verify one live v41 checkpoint against its flat-boundary evidence."""
    _require_v41_config(config)
    readiness_identity = _require_readiness(readiness, config)
    now = _aware_utc(now_utc, "acceptance clock")
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
    reasons = _check_reasons(checks)
    return {
        "schema_version": "v41_poststart_acceptance_v1",
        "contract": _contract(),
        "accepted": not reasons,
        "decision": "accepted" if not reasons else "rejected",
        "reasons": reasons,
        "run": dict(mapping(audit.get("run"), "checkpoint run")),
        "readiness_identity": readiness_identity,
        "checks": checks,
        "limitations": _limitations(),
    }


def _require_v41_config(config: MultiAssetLiveConfig) -> None:
    exact = (
        config.profile_id == _PROFILE_ID
        and config.profile_fingerprint == _PROFILE_FINGERPRINT
        and config.network == "mainnet"
        and config.margin_mode == "isolated"
        and config.maximum_positions == 10
        and len(config.assets) == 8
        and len(config.providers) == 7
        and len(config.executable_provider_symbols) == 14
        and len(config.executable_provider_directions) == 28
        and math.isclose(
            sum(asset.margin_fraction for asset in config.assets),
            0.24,
            abs_tol=1e-12,
        )
        and all(asset.leverage == 5.0 for asset in config.assets)
    )
    if not exact:
        raise ValueError("post-start acceptance requires the exact v41 profile")


def _require_readiness(
    readiness: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    if readiness.get("schema_version") != "v41_successor_readiness_v1":
        raise ValueError("v41 readiness schema does not match")
    contract = mapping(readiness.get("contract"), "v41 readiness contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("v41 readiness contract is not report-only")
    candidate = mapping(readiness.get("candidate"), "v41 readiness candidate")
    if (
        candidate.get("profile_id") != config.profile_id
        or candidate.get("profile_fingerprint") != config.profile_fingerprint
    ):
        raise ValueError("v41 readiness identity does not match config")
    assessment = mapping(readiness.get("assessment"), "v41 readiness assessment")
    if assessment.get("sizing_technically_coherent") is not True:
        raise ValueError("v41 readiness sizing is not technically coherent")
    if assessment.get("transition_ready_now") is not True:
        raise ValueError("v41 readiness is not transition-ready")
    return {
        "material_state_sha256": _text(
            readiness.get("material_state_sha256"), "readiness digest"
        ),
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "profit_optimality_proven": assessment.get("profit_optimality_proven"),
    }


def _check_reasons(checks: Record) -> list[str]:
    reasons: list[str] = []
    for value in checks.values():
        check = mapping(value, "v41 acceptance check")
        raw = check.get("reasons")
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise ValueError("v41 acceptance reasons must be strings")
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


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"maximum {label} must be positive and finite")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _limitations() -> list[str]:
    return [
        "technical post-start acceptance does not establish route profitability",
        "the accepted readiness artifact must come from the final flat boundary",
        "zero fills can verify runtime shape but not realized friction economics",
        "this report cannot route, resize, pause, retune, or submit an order",
    ]
