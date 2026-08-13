"""Pure completeness labels for Apex MM live audit evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.live.hyperliquid_fill_identity import (
    FillKey,
    fill_identity_gaps,
    ledger_fill_keys,
)
from hypervector.research.apex_mm_live_audit_quality import metric_coverage_status


Record = Mapping[str, object]


@dataclass(frozen=True)
class ApexCoverageEvidence:
    """Inputs required to judge exact live-evidence completeness."""

    records: Sequence[Record]
    fills: Sequence[Record]
    acknowledgements: Sequence[Record]
    qualities: Sequence[Record]
    markouts: Sequence[Record]
    positions: Sequence[Record]
    distances: Sequence[Record]
    funding: Sequence[Record]
    evidence_gaps: Sequence[str]
    markout_horizon_valid: bool
    quote_freshness_status: str
    reconstructed_inventory: float
    reconstructed_final: float
    observed_final: object


@dataclass(frozen=True)
class _CoverageFacts:
    fill_keys: set[FillKey]
    fee_keys: set[FillKey]
    quality_keys: set[FillKey]
    markout_keys: set[FillKey]
    active_inventory: bool
    observed_inventory: bool
    measured_latency: int


def audit_coverage(evidence: ApexCoverageEvidence) -> dict[str, object]:
    """Report exact fill-linked metric coverage and technical gaps."""
    facts = _coverage_facts(evidence)
    gaps = _coverage_gaps(evidence, facts)
    metrics = _coverage_metrics(
        evidence=evidence,
        measured_latency=facts.measured_latency,
        orphan_quality=facts.quality_keys - facts.fill_keys,
        orphan_markout=facts.markout_keys - facts.fill_keys,
        active_inventory=facts.active_inventory,
    )
    unique_gaps = sorted(set(gaps))
    return {
        "complete": not unique_gaps,
        "technical_gaps": unique_gaps,
        "metrics": metrics,
    }


def _coverage_facts(evidence: ApexCoverageEvidence) -> _CoverageFacts:
    fill_keys = ledger_fill_keys(
        evidence.fills, timestamp_key="venue_timestamp_ms", label="Apex fill"
    )
    quality_keys = ledger_fill_keys(
        evidence.qualities,
        timestamp_key="fill_timestamp_ms",
        label="Apex slippage",
    )
    markout_keys = ledger_fill_keys(
        evidence.markouts,
        timestamp_key="fill_timestamp_ms",
        label="Apex markout",
    )
    fee_keys = ledger_fill_keys(
        _fill_fee_rows(evidence.records),
        timestamp_key="venue_timestamp_ms",
        label="Apex fee",
    )
    active_inventory = any(
        _number(row, "size_signed") != 0.0 for row in evidence.positions
    )
    observed_inventory = any(
        abs(_number(row, "position_value_usd")) > 0.0 for row in evidence.positions
    )
    measured_latency = sum(
        _optional_number(row, "round_trip_latency_ms") is not None
        for row in evidence.acknowledgements
    )
    return _CoverageFacts(
        fill_keys=fill_keys,
        fee_keys=fee_keys,
        quality_keys=quality_keys,
        markout_keys=markout_keys,
        active_inventory=active_inventory,
        observed_inventory=observed_inventory,
        measured_latency=measured_latency,
    )


def _coverage_gaps(
    evidence: ApexCoverageEvidence,
    facts: _CoverageFacts,
) -> list[str]:
    orphan_quality = facts.quality_keys - facts.fill_keys
    orphan_markout = facts.markout_keys - facts.fill_keys
    gaps = metric_gaps(
        fill_count=len(evidence.fills),
        acknowledgement_count=len(evidence.acknowledgements),
        measured_latency=facts.measured_latency,
        quality_count=len(evidence.qualities),
        markout_count=len(evidence.markouts),
        orphan_quality=orphan_quality,
        orphan_markout=orphan_markout,
    )
    gaps.extend(
        inventory_gaps(
            active_inventory=facts.active_inventory,
            observed_inventory=facts.observed_inventory,
            reconstructed_inventory=evidence.reconstructed_inventory,
            distance_count=len(evidence.distances),
        )
    )
    gaps.extend(evidence.evidence_gaps)
    gaps.extend(fill_identity_gaps(facts.fill_keys, facts.fee_keys, label="fee"))
    gaps.extend(
        fill_identity_gaps(facts.fill_keys, facts.quality_keys, label="slippage")
    )
    gaps.extend(
        fill_identity_gaps(facts.fill_keys, facts.markout_keys, label="markout")
    )
    gaps.extend(
        final_inventory_gaps(evidence.reconstructed_final, evidence.observed_final)
    )
    return gaps


def final_inventory_gaps(
    reconstructed_final: float,
    observed_final: object,
) -> list[str]:
    """Reject a venue position that cannot be rebuilt from journaled fills."""
    if (
        isinstance(observed_final, bool)
        or not isinstance(observed_final, (int, float))
        or not math.isfinite(float(observed_final))
    ):
        return []
    return (
        ["fill_inventory_reconciliation_mismatch"]
        if abs(reconstructed_final - float(observed_final)) > 1e-12
        else []
    )


def coverage_status(required: int, observed: int, empty: str) -> str:
    """Label whether a count-backed metric is applicable and complete."""
    if required == 0:
        return empty
    return "observed" if observed >= required else "missing"


def inventory_coverage_status(
    position_count: int,
    active_inventory: bool,
    filled_inventory: bool,
) -> str:
    """Label observed versus fill-only reconstructed inventory coverage."""
    if filled_inventory and not active_inventory:
        return "partial_reconstructed_only"
    return "observed" if position_count else "not_observed"


def metric_gaps(
    *,
    fill_count: int,
    acknowledgement_count: int,
    measured_latency: int,
    quality_count: int,
    markout_count: int,
    orphan_quality: set[object],
    orphan_markout: set[object],
) -> list[str]:
    """Return missing or orphan execution-measurement evidence."""
    gaps: list[str] = []
    if acknowledgement_count and measured_latency < acknowledgement_count:
        gaps.append("acknowledgement_latency_missing")
    if fill_count and quality_count < fill_count:
        gaps.append("slippage_missing_for_fills")
    if fill_count and markout_count < fill_count:
        gaps.append("markout_missing_for_fills")
    if orphan_quality:
        gaps.append("slippage_without_run_fill")
    if orphan_markout:
        gaps.append("markout_without_run_fill")
    return gaps


def inventory_gaps(
    *,
    active_inventory: bool,
    observed_inventory: bool,
    reconstructed_inventory: float,
    distance_count: int,
) -> list[str]:
    """Return missing inventory and liquidation-distance evidence."""
    gaps: list[str] = []
    if active_inventory and not distance_count:
        gaps.append("liquidation_distance_missing_for_inventory")
    if reconstructed_inventory > 0.0 and not observed_inventory:
        gaps.append("inventory_path_missing_for_fills")
    if reconstructed_inventory > 0.0 and not distance_count:
        gaps.append("liquidation_distance_missing_for_filled_inventory")
    return gaps


def _coverage_metrics(
    *,
    evidence: ApexCoverageEvidence,
    measured_latency: int,
    orphan_quality: set[object],
    orphan_markout: set[object],
    active_inventory: bool,
) -> dict[str, str]:
    fill_count = len(evidence.fills)
    filled_inventory = evidence.reconstructed_inventory > 0.0
    metrics = {
        "latency": coverage_status(
            len(evidence.acknowledgements),
            measured_latency,
            "not_applicable_no_acknowledgements",
        ),
        "fees": "observed" if fill_count else "not_applicable_no_fills",
        "funding": ("observed" if evidence.funding else "not_observed_no_settlement"),
        "slippage": metric_coverage_status(
            fill_count, len(evidence.qualities), orphan_quality
        ),
        "markout": _markout_status(evidence, orphan_markout),
        "inventory": inventory_coverage_status(
            len(evidence.positions), active_inventory, filled_inventory
        ),
        "liquidation_distance": coverage_status(
            int(active_inventory or filled_inventory),
            len(evidence.distances),
            "not_applicable_flat",
        ),
        "quote_freshness": evidence.quote_freshness_status,
    }
    return metrics


def _markout_status(
    evidence: ApexCoverageEvidence,
    orphan_markout: set[object],
) -> str:
    if evidence.markouts and not orphan_markout and not evidence.markout_horizon_valid:
        return "observed_outside_horizon"
    return metric_coverage_status(
        len(evidence.fills), len(evidence.markouts), orphan_markout
    )


def _fill_fee_rows(records: Sequence[Record]) -> list[Record]:
    return [
        row
        for row in records
        if row.get("event_type") == "fee" and _payload(row).get("source") == "fill"
    ]


def _number(record: Record, key: str) -> float:
    value = _payload(record).get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    observed = float(value)
    if not math.isfinite(observed):
        raise ValueError(f"{key} must be finite")
    return observed


def _optional_number(record: Record, key: str) -> float | None:
    value = _payload(record).get(key)
    return None if value is None else _number(record, key)


def _payload(record: Record) -> Mapping[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("live record payload must be an object")
    return payload
