"""Technical coverage and learning-state summaries for cohort audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import event_rows, integer, mapping

Record = Mapping[str, object]


def build_coverage(
    records: Sequence[Record],
    symbols: Sequence[str],
    readiness: Mapping[str, object],
    signal_outcomes: Mapping[str, object],
    execution: Mapping[str, object],
    health: Mapping[str, object],
) -> dict[str, object]:
    """Report technical evidence gaps without creating performance gates."""
    gaps: list[str] = []
    if not event_rows(records, "cohort_snapshot"):
        gaps.append("cohort_snapshots_missing")
    if readiness.get("missing_provider_symbols"):
        gaps.append("provider_readiness_missing")
    signal_coverage = mapping(
        signal_outcomes.get("coverage"), "signal outcome coverage"
    )
    if signal_coverage.get("market_data_complete") is not True:
        gaps.append("signal_outcome_market_data_missing")
    if signal_coverage.get("metric_telemetry_complete") is not True:
        gaps.append("provider_metric_telemetry_missing")
    if integer(signal_coverage, "direction_conflicts"):
        gaps.append("provider_direction_telemetry_conflict")
    if execution.get("fills") != execution.get("projected_fills"):
        gaps.append("cohort_fill_projection_mismatch")
    _add_asset_gaps(gaps, symbols, health)
    if integer(health, "faults"):
        gaps.append("faults_recorded")
    unique = sorted(set(gaps))
    return {"complete": not unique, "technical_gaps": unique}


def learning_summary(
    execution: Mapping[str, object], coverage: Mapping[str, object]
) -> dict[str, object]:
    """Describe the evidence state without inferring a strategy edge."""
    trades = integer(execution, "closed_trades")
    state = "no_closed_trade_evidence" if trades == 0 else "descriptive_trade_evidence"
    next_evidence = []
    if coverage.get("complete") is not True:
        next_evidence.append(
            "resolve_technical_coverage_gaps_before_economic_attribution"
        )
    next_evidence.append(
        "collect_forward_live_entries_and_resolved_exits"
        if trades == 0
        else "compare_strategy_side_results_across_independent_live_windows"
    )
    return {
        "evidence_state": state,
        "strategy_edge_identifiable": False,
        "performance_claim": "not_established",
        "next_evidence": next_evidence,
    }


def _add_asset_gaps(
    gaps: list[str], symbols: Sequence[str], health: Mapping[str, object]
) -> None:
    assets = mapping(health.get("assets"), "health assets")
    for symbol in symbols:
        values = mapping(assets.get(symbol), f"{symbol} health")
        if values.get("final_state") is None:
            gaps.append(f"{symbol.lower()}_final_state_missing")
        if values.get("protected_if_open") is not True:
            gaps.append(f"{symbol.lower()}_open_position_unprotected")
