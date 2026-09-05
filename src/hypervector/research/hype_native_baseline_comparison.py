"""Exact same-bar comparison of HYPE native and compression evaluations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    nonnegative_int,
    number,
    object_list,
    payload,
    text,
    text_list,
)
from hypervector.research.cohort_signal_candidates import SignalCandidate

Record = Mapping[str, object]
HYPE_COMPRESSION_BASELINE_STRATEGY_ID = (
    "hype_breakout_compression_alignment_bidirectional_v2"
)
_COMMON_FEATURES = (
    "authoritative_5m_bbwp_percentile",
    "breakout_onset",
    "breakout_side",
    "breakout_side_relation",
    "breakout_volume_ratio",
    "current_bbwp_percentile",
    "directional_bar_body_bps",
    "ema_gap_directional_bps",
    "prior_bbwp_min_15m",
    "structural_direction",
)


def build_hype_native_baseline_comparisons(
    records: Sequence[Record],
    native_entries: Sequence[SignalCandidate],
) -> list[dict[str, object]]:
    """Explain each eligible native entry against the same-bar v53 route."""
    indexed = _evaluation_index(records)
    output: list[dict[str, object]] = []
    for entry in sorted(native_entries, key=lambda row: row.decision_time_ms):
        native = _required_evaluation(indexed, entry, entry.strategy_id)
        baseline = _required_evaluation(
            indexed,
            entry,
            HYPE_COMPRESSION_BASELINE_STRATEGY_ID,
        )
        output.append(_comparison(entry, native, baseline))
    return output


def _evaluation_index(
    records: Sequence[Record],
) -> dict[tuple[str, str, int], Record]:
    result: dict[tuple[str, str, int], Record] = {}
    for row in event_rows(records, "intent_routing"):
        for evaluation in object_list(payload(row), "evaluations", required=False):
            key = _evaluation_key(evaluation)
            prior = result.get(key)
            if prior is not None and prior != evaluation:
                raise ValueError("conflicting duplicate HYPE baseline evaluation")
            result[key] = evaluation
    return result


def _evaluation_key(evaluation: Record) -> tuple[str, str, int]:
    return (
        text(evaluation.get("strategy_id"), "HYPE comparison strategy id"),
        text(evaluation.get("symbol"), "HYPE comparison symbol"),
        nonnegative_int(
            evaluation.get("decision_time_ms"),
            "HYPE comparison decision time",
        ),
    )


def _required_evaluation(
    indexed: Mapping[tuple[str, str, int], Record],
    entry: SignalCandidate,
    strategy_id: str,
) -> Record:
    key = (strategy_id, entry.symbol, entry.decision_time_ms)
    evaluation = indexed.get(key)
    if evaluation is None:
        raise ValueError("eligible HYPE native entry lacks exact baseline comparison")
    reference = number(evaluation.get("reference_price"), "comparison reference price")
    if reference != entry.reference_price:
        raise ValueError("HYPE native and baseline reference prices differ")
    return evaluation


def _comparison(
    entry: SignalCandidate,
    native: Record,
    baseline: Record,
) -> dict[str, object]:
    if (
        native.get("eligible") is not True
        or native.get("decision_action") != "enter_long"
    ):
        raise ValueError("HYPE native comparison entry contract is invalid")
    baseline_eligible = baseline.get("eligible")
    if not isinstance(baseline_eligible, bool):
        raise ValueError("HYPE baseline eligibility must be boolean")
    _require_baseline_action(baseline, baseline_eligible)
    readiness = mapping(baseline.get("readiness"), "HYPE baseline readiness")
    _require_feature_parity(native, baseline)
    return {
        "symbol": entry.symbol,
        "decision_time_ms": entry.decision_time_ms,
        "reference_price": entry.reference_price,
        "native_strategy_id": entry.strategy_id,
        "native_eligible": True,
        "baseline_strategy_id": HYPE_COMPRESSION_BASELINE_STRATEGY_ID,
        "baseline_eligible": baseline_eligible,
        "baseline_reason": text(baseline.get("reason"), "HYPE baseline reason"),
        "baseline_blockers": text_list(
            readiness.get("blockers"), "HYPE baseline blockers"
        ),
        "baseline_conditions_met": nonnegative_int(
            readiness.get("conditions_met"), "HYPE baseline conditions met"
        ),
        "baseline_conditions_required": _positive_int(
            readiness.get("conditions_required"), "HYPE baseline conditions required"
        ),
        "common_feature_parity": True,
        "opportunity_class": _opportunity_class(baseline_eligible),
    }


def _require_baseline_action(baseline: Record, eligible: bool) -> None:
    expected = "enter_long" if eligible else "hold"
    if baseline.get("side") != "long" or baseline.get("decision_action") != expected:
        raise ValueError("HYPE baseline action contract is invalid")


def _require_feature_parity(native: Record, baseline: Record) -> None:
    native_metrics = mapping(
        mapping(native.get("readiness"), "HYPE native readiness").get("metrics"),
        "HYPE native metrics",
    )
    baseline_metrics = mapping(
        mapping(baseline.get("readiness"), "HYPE baseline readiness").get("metrics"),
        "HYPE baseline metrics",
    )
    for field in _COMMON_FEATURES:
        if field not in native_metrics or native_metrics[field] != baseline_metrics.get(
            field
        ):
            raise ValueError(f"HYPE native and baseline {field} differ")


def _positive_int(value: object, label: str) -> int:
    result = nonnegative_int(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _opportunity_class(baseline_eligible: bool) -> str:
    if baseline_eligible:
        return "native_breakout_and_compression_pullback_both_admitted"
    return "native_breakout_admitted_compression_pullback_rejected"
