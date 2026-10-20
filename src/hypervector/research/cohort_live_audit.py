"""Report-only evidence audit for one shared multi-asset live cohort run."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from hypervector.live.sol_range_onset_live_journal import build_live_journal
from hypervector.research.cohort_canonical_regime_telemetry import (
    build_canonical_regime_telemetry_summary,
)
from hypervector.research.cohort_live_audit_coverage import (
    build_coverage,
    learning_summary,
)
from hypervector.research.cohort_live_audit_execution import (
    execution_summary,
    history_run_ids,
)
from hypervector.research.cohort_live_audit_health import health_summary
from hypervector.research.cohort_live_audit_history import (
    select_all_time_asset_evidence,
    select_asset_evidence,
)
from hypervector.research.cohort_live_audit_routing import build_routing_summary
from hypervector.research.cohort_live_audit_values import (
    configured_symbols as _configured_symbols,
)
from hypervector.research.cohort_live_audit_values import (
    expected_provider_pairs as _expected_provider_pairs,
)
from hypervector.research.cohort_live_audit_values import (
    mapping as _mapping,
)
from hypervector.research.cohort_live_audit_values import (
    mapping_list as _mapping_list,
)
from hypervector.research.cohort_live_audit_values import (
    provider_cadence_minutes as _provider_cadence_minutes,
)
from hypervector.research.cohort_live_audit_values import (
    run_id as _run_id,
)
from hypervector.research.cohort_live_audit_values import (
    text as _text,
)
from hypervector.research.cohort_live_audit_values import (
    timestamp as _timestamp,
)
from hypervector.research.cohort_live_run_selection import select_armed_live_run
from hypervector.research.cohort_live_audit_summaries import (
    experiment_contract,
    limitations,
    portfolio_summary,
    readiness_summary,
    rebased,
    run_summary,
    runtime_summary,
    scorecard_pairs,
    validated_records,
)
from hypervector.research.cohort_entry_alignment_mechanism import (
    build_live_entry_alignment_mechanism,
)
from hypervector.research.cohort_ignored_provider_exit_scorecard import (
    build_ignored_provider_exit_policy_scorecard,
)
from hypervector.research.cohort_maximum_hold_decisions import (
    build_maximum_hold_decision_evidence,
)
from hypervector.research.cohort_maximum_hold_extension_outcomes import (
    build_maximum_hold_extension_outcomes,
)
from hypervector.research.cohort_mature_profit_floor import (
    build_mature_profit_floor_mechanism,
)
from hypervector.research.cohort_open_trade_reflections import (
    build_open_trade_reflections,
)
from hypervector.research.cohort_profit_lock_challenger import (
    build_all_time_profit_lock_mechanism,
    build_profit_lock_challenger,
    build_regime_conditioned_profit_lock_mechanism,
    build_support_decay_profit_lock_mechanism,
)
from hypervector.research.cohort_risk_normalized_profit_lock import (
    build_risk_normalized_profit_lock_mechanism,
)
from hypervector.research.cohort_provider_episode_reentry import (
    build_provider_episode_reentry,
)
from hypervector.research.cohort_provider_contract_history import (
    build_provider_contract_history,
)
from hypervector.research.cohort_regime_conflict_journal import (
    build_regime_conflict_journal,
)
from hypervector.research.cohort_signal_orderbook_context import (
    build_orderbook_opportunity_diagnostics,
)
from hypervector.research.cohort_signal_outcomes import (
    build_provider_forward_diagnostics,
)
from hypervector.research.cohort_strategy_scorecard import (
    build_strategy_scorecard,
)
from hypervector.research.cohort_trade_reflections import (
    build_all_time_trade_reflections,
    build_trade_reflections,
)

Record = Mapping[str, object]


def audit_multi_asset_live_run(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    *,
    all_time_asset_records: Mapping[str, Sequence[Record]] | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    """Build a non-mutating technical and economic audit of one live run."""
    cohort = validated_records(cohort_records, "cohort")
    selected, identity = select_armed_live_run(cohort, run_id)
    symbols = _configured_symbols(identity)
    asset_cutoff = _latest_snapshot_time(selected)
    selected_assets, history_assets = select_asset_evidence(
        asset_records,
        symbols,
        _run_id(identity),
        as_of=asset_cutoff,
    )
    all_time_source = all_time_asset_records or asset_records
    all_time_symbols = tuple(sorted(all_time_source))
    all_time_assets = select_all_time_asset_evidence(
        all_time_source,
        all_time_symbols,
        _run_id(identity),
        as_of=asset_cutoff,
    )
    journals = {
        symbol: build_live_journal(rebased(rows))
        for symbol, rows in history_assets.items()
    }
    all_time_journals = {
        symbol: build_live_journal(rebased(rows))
        for symbol, rows in all_time_assets.items()
    }
    classification = _classification_evidence(selected, identity, selected_assets)
    execution = _execution_evidence(
        cohort,
        selected,
        identity,
        selected_assets,
        history_assets,
        journals,
        all_time_assets,
        all_time_journals,
    )
    classification["strategy_scorecard"] = _live_scorecard(
        identity, classification, execution
    )
    health = health_summary(selected, selected_assets)
    coverage = build_coverage(
        selected,
        symbols,
        _mapping(classification["readiness"], "readiness"),
        _mapping(classification["signal_outcomes"], "signal outcomes"),
        _mapping(execution["execution"], "execution"),
        health,
    )
    return _audit_document(
        selected,
        identity,
        symbols,
        selected_assets,
        classification | execution,
        health,
        coverage,
    )


def _latest_snapshot_time(selected: Sequence[Record]) -> datetime:
    """Bind asset evidence to the latest authoritative portfolio snapshot."""
    snapshots = tuple(
        row for row in selected if row.get("event_type") == "cohort_snapshot"
    )
    if not snapshots:
        raise ValueError("cohort audit requires a portfolio snapshot")
    return _timestamp(snapshots[-1])


def _live_scorecard(
    identity: Record,
    classification: Mapping[str, object],
    execution: Mapping[str, object],
) -> dict[str, object]:
    reflections = _mapping(execution.get("trade_reflections"), "trade reflections")
    contract_history = _mapping(
        reflections.get("provider_contract_history"),
        "provider contract history",
    )
    performance = _mapping(
        contract_history.get("performance"), "provider contract performance"
    )
    repeatability = _mapping(
        contract_history.get("repeatability"),
        "provider contract repeatability",
    )
    readiness = _mapping(classification.get("readiness"), "readiness")
    return build_strategy_scorecard(
        scorecard_pairs(identity),
        _mapping(readiness.get("by_provider_symbol"), "readiness providers"),
        _mapping(classification.get("signal_outcomes"), "signal outcomes"),
        execution_by_pair=_mapping(
            performance.get("by_provider_symbol"), "provider-symbol performance"
        ),
        repeatability_by_pair=_mapping(
            repeatability.get("by_provider_symbol"),
            "provider-symbol repeatability",
        ),
        execution_scope=_text(contract_history.get("scope"), "provider contract scope"),
    )


def _classification_evidence(
    selected: Sequence[Record],
    identity: Record,
    selected_assets: Mapping[str, Sequence[Record]],
) -> dict[str, object]:
    readiness = readiness_summary(selected, identity)
    signal_outcomes = build_provider_forward_diagnostics(selected)
    return {
        "canonical_regime_telemetry": build_canonical_regime_telemetry_summary(
            selected
        ),
        "routing": build_routing_summary(selected, identity),
        "readiness": readiness,
        "signal_outcomes": signal_outcomes,
        "orderbook_opportunity": build_orderbook_opportunity_diagnostics(
            selected,
            selected_assets,
            provider_cadence_minutes=_provider_cadence_minutes(identity),
        ),
        "regime_conflict_journal": build_regime_conflict_journal(selected, identity),
    }


def _execution_evidence(
    cohort: Sequence[Record],
    selected: Sequence[Record],
    identity: Record,
    selected_assets: Mapping[str, Sequence[Record]],
    history_assets: Mapping[str, Sequence[Record]],
    journals: Mapping[str, Mapping[str, object]],
    all_time_assets: Mapping[str, Sequence[Record]],
    all_time_journals: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    compatible_run_ids = history_run_ids(history_assets)
    trade_reflections = build_trade_reflections(
        cohort,
        journals,
        asset_records=history_assets,
        compatible_run_ids=compatible_run_ids,
        current_profile_fingerprint=_text(
            identity.get("profile_fingerprint"), "current profile fingerprint"
        ),
        current_run_id=_run_id(identity),
    )
    all_time_live = build_all_time_trade_reflections(
        cohort,
        all_time_journals,
        asset_records=all_time_assets,
        live_run_ids=history_run_ids(all_time_assets),
    )
    provider_contract_history = build_provider_contract_history(
        cohort,
        identity,
        _mapping_list(all_time_live.get("trades"), "all-time reflected trades"),
    )
    performance = _mapping(trade_reflections.get("performance"), "trade performance")
    performance["all_time_live"] = _mapping(
        all_time_live.get("performance"), "all-time live performance"
    )
    trade_reflections["all_time_live"] = all_time_live
    trade_reflections["provider_contract_history"] = provider_contract_history
    execution = execution_summary(
        selected,
        selected_assets,
        history_assets,
        journals,
        identity,
    )
    open_trade_reflections = build_open_trade_reflections(
        cohort,
        selected,
        journals,
        history_assets,
        _mapping_list(execution.get("open_positions"), "open positions"),
        compatible_run_ids=compatible_run_ids,
        current_run_id=_run_id(identity),
    )
    compatible_cohort = tuple(
        row for row in cohort if row.get("run_id") in compatible_run_ids
    )
    reflected_trades = _mapping_list(
        trade_reflections.get("trades"), "reflected trades"
    )
    open_reflected_trades = _mapping_list(
        open_trade_reflections.get("trades"), "open reflected trades"
    )
    resolved = _resolved_exit_evidence(
        selected,
        identity,
        compatible_cohort,
        history_assets,
        reflected_trades,
        open_reflected_trades=open_reflected_trades,
        all_time_cohort=cohort,
        all_time_assets=all_time_assets,
        all_time_reflected_trades=_mapping_list(
            all_time_live.get("trades"), "all-time reflected trades"
        ),
    )
    return {
        "execution": execution,
        "open_trade_reflections": open_trade_reflections,
        "trade_reflections": trade_reflections,
        "ignored_provider_exit_policy_scorecard": (
            build_ignored_provider_exit_policy_scorecard(
                closed_trades=reflected_trades,
                open_trades=open_reflected_trades,
            )
        ),
        **resolved,
    }


def _resolved_exit_evidence(
    selected: Sequence[Record],
    identity: Record,
    compatible_cohort: Sequence[Record],
    history_assets: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
    *,
    open_reflected_trades: Sequence[Record],
    all_time_cohort: Sequence[Record],
    all_time_assets: Mapping[str, Sequence[Record]],
    all_time_reflected_trades: Sequence[Record],
) -> dict[str, object]:
    maximum_hold = build_maximum_hold_decision_evidence(
        selected,
        _expected_provider_pairs(identity),
    )
    maximum_hold["extension_outcomes"] = build_maximum_hold_extension_outcomes(
        compatible_cohort,
        history_assets,
        reflected_trades,
    )
    profit_lock = build_profit_lock_challenger(
        compatible_cohort,
        history_assets,
        reflected_trades,
        current_profile_fingerprint=_text(
            identity.get("profile_fingerprint"), "current profile fingerprint"
        ),
        current_run_id=_run_id(identity),
    )
    profit_lock["all_time_live_mechanism"] = build_all_time_profit_lock_mechanism(
        all_time_cohort,
        all_time_assets,
        all_time_reflected_trades,
    )
    profit_lock["mature_profit_floor_all_time_live_mechanism"] = (
        build_mature_profit_floor_mechanism(
            all_time_cohort,
            all_time_assets,
            all_time_reflected_trades,
        )
    )
    profit_lock["risk_normalized_all_time_live_mechanism"] = (
        build_risk_normalized_profit_lock_mechanism(
            all_time_cohort,
            all_time_assets,
            all_time_reflected_trades,
        )
    )
    profit_lock["regime_conditioned_all_time_live_mechanism"] = (
        build_regime_conditioned_profit_lock_mechanism(
            all_time_cohort,
            all_time_assets,
            all_time_reflected_trades,
        )
    )
    profit_lock["support_decay_all_time_live_mechanism"] = (
        build_support_decay_profit_lock_mechanism(
            all_time_cohort,
            all_time_assets,
            all_time_reflected_trades,
        )
    )
    return {
        "maximum_hold_decisions": maximum_hold,
        "profit_lock_challenger": profit_lock,
        "entry_alignment_mechanism": build_live_entry_alignment_mechanism(
            all_time_reflected_trades,
            open_trades=open_reflected_trades,
        ),
        "provider_episode_reentry": build_provider_episode_reentry(
            all_time_cohort,
            all_time_reflected_trades,
            open_trades=open_reflected_trades,
        ),
    }


def _audit_document(
    selected: Sequence[Record],
    identity: Record,
    symbols: tuple[str, ...],
    selected_assets: Mapping[str, Sequence[Record]],
    evidence: Mapping[str, object],
    health: Mapping[str, object],
    coverage: Mapping[str, object],
) -> dict[str, object]:
    execution = _mapping(evidence.get("execution"), "execution")
    return {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_audit",
        "experiment_contract": experiment_contract(),
        "run": run_summary(selected, identity, symbols),
        "runtime": runtime_summary(selected, selected_assets),
        "portfolio": portfolio_summary(selected),
        **evidence,
        "health": health,
        "coverage": coverage,
        "learning": learning_summary(execution, coverage),
        "limitations": limitations(),
    }
