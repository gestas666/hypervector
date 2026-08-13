"""Exact identity and contract boundary for v31 raw-ledger acceptance."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    text,
)

Record = Mapping[str, object]

_CANDIDATE_PROFILE = "multi_asset_bidirectional_swing_pruned_candidate_v31"
V31_SYMBOLS: tuple[str, ...] = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:GOLD",
    "xyz:BRENTOIL",
)


def raw_acceptance_contract() -> dict[str, object]:
    """Return the immutable verifier's execution-incapable contract."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_transition": False,
        "runtime_strategy_changed": False,
    }


def raw_acceptance_identity(
    checkpoint: Record,
    aggregate: Record,
    *,
    expected_profile_id: str = _CANDIDATE_PROFILE,
) -> tuple[dict[str, str], list[str]]:
    """Validate exact checkpoint/aggregate identity and return rejection reasons."""
    if not expected_profile_id.strip():
        raise ValueError("expected profile ID must be nonempty")
    contract = mapping(aggregate.get("contract"), "aggregate contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("aggregate acceptance is not report-only")
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    run = mapping(audit.get("run"), "checkpoint run")
    aggregate_run = mapping(aggregate.get("run"), "aggregate run")
    identity = {
        field: text(run.get(field), f"run {field}")
        for field in ("run_id", "profile_id", "profile_fingerprint")
    }
    matching = all(
        aggregate_run.get(field) == value for field, value in identity.items()
    )
    active = identity["profile_id"] == expected_profile_id
    reasons: list[str] = []
    if aggregate.get("accepted") is not True:
        reasons.append("aggregate_acceptance_rejected")
    if not active or not matching:
        reasons.append("candidate_identity_not_active")
    return identity, reasons


def raw_acceptance_limitations() -> list[str]:
    """Return explicit boundaries on the raw-ledger technical claim."""
    return [
        "cursor continuity proves query-window coverage, not venue API completeness",
        "inclusive boundary repetition is deduplicated by transaction identity",
        "raw technical acceptance does not establish fillability or expectancy",
        "the verifier has no transition, execution, sizing, or promotion authority",
    ]


def is_run_event(row: Record, identity: Record, event_type: str) -> bool:
    """Return an exact cohort-run event and reject authority/profile drift."""
    if row.get("run_id") != identity["run_id"] or row.get("event_type") != event_type:
        return False
    if row.get("profile_id") != identity["profile_id"]:
        raise ValueError("cohort ledger profile identity drifted")
    _require_live_authority(row)
    return True


def is_asset_event(row: Record, identity: Record, event_type: str) -> bool:
    """Return an exact asset-run event and reject execution-authority drift."""
    if row.get("run_id") != identity["run_id"] or row.get("event_type") != event_type:
        return False
    _require_live_authority(row)
    return True


def ledger_timestamp_ms(row: Record) -> int:
    """Return one timezone-aware ledger observation in epoch milliseconds."""
    value = text(row.get("observed_at_utc"), "ledger observation time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("ledger observation time must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def ledger_sequence(row: Record, label: str) -> int:
    """Return one nonnegative ledger sequence."""
    return nonnegative_int(row.get("sequence"), f"{label} sequence")


def boolean_value(value: object, label: str) -> bool:
    """Return one strict boolean value."""
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _require_live_authority(row: Record) -> None:
    if (
        row.get("execution_mode") != "live"
        or row.get("live_armed") is not True
        or row.get("execution_authority") != "hyperliquid_mainnet"
    ):
        raise ValueError("raw ledger evidence is not armed mainnet telemetry")
