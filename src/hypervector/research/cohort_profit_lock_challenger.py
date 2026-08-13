"""Causal report-only profit-lock challengers for resolved live lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import mapping, nonnegative_int, text
from hypervector.research.cohort_profit_lock_lifecycle import (
    build_profit_lock_lifecycle_results,
    build_regime_conditioned_lifecycle_results,
    build_support_decay_lifecycle_results,
)
from hypervector.research.cohort_profit_lock_policy import (
    POLICIES,
    policy_declaration,
)
from hypervector.research.cohort_profit_lock_summary import (
    grouped_summaries,
    summaries,
)

Record = Mapping[str, object]
_LATEST_LIMIT = 50
_REGIME_PERSISTENCE_DECISIONS = 5
_REGIME_OPPOSITION_THRESHOLD = -0.5
_SUPPORT_DECAY_THRESHOLD = 0.25
_MINUTE_MS = 60_000
_POLICY_IDS = tuple(policy.policy_id for policy in POLICIES)
_HIP3_SWING_POLICY_ID = "a60_floor15_trail30"
_HIP3_SWING_HYPOTHESIS_ID = "hip3-swing-profit-lock"
_HIP3_SWING_PREDECLARED_AT_UTC = "2026-08-09T04:04:06Z"
_HIP3_SWING_ENTRY_CUTOFF_MS = 1_786_248_246_000
_HIP3_SWING_SCOPE = {
    "hip3_swing_ha_sp500_spcx_bidirectional_v2": frozenset({"xyz:SP500", "xyz:SPCX"}),
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1": frozenset(
        {"xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"}
    ),
}


def build_profit_lock_challenger(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
    *,
    current_profile_fingerprint: str,
    current_run_id: str,
) -> dict[str, object]:
    """Compare actual exits with frozen causal profit-lock counterfactuals."""
    profile = text(current_profile_fingerprint, "current profile fingerprint")
    run_id = text(current_run_id, "current run id")
    results = build_profit_lock_lifecycle_results(
        cohort_records, asset_records, reflected_trades
    )
    return _report(results, profile, run_id)


def build_all_time_profit_lock_mechanism(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> dict[str, object]:
    """Build normalized, report-only exit-mechanism evidence across live history."""
    from hypervector.research.cohort_profit_lock_mechanism import (
        build_normalized_profit_lock_report,
    )

    results = build_profit_lock_lifecycle_results(
        cohort_records, asset_records, reflected_trades
    )
    return build_normalized_profit_lock_report(
        results,
        policies=[policy_declaration(policy) for policy in POLICIES],
        contract=_contract(),
        limitations=_limitations(),
    )


def build_hip3_swing_60_30_prospective_mechanism(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> dict[str, object]:
    """Score only HIP-3 Swing/HA entries opened after the hypothesis cutoff."""
    from hypervector.research.cohort_profit_lock_mechanism import (
        build_normalized_profit_lock_report,
    )

    matching = [trade for trade in reflected_trades if _is_hip3_swing_trade(trade)]
    prospective = [
        trade
        for trade in matching
        if _entry_timestamp_ms(trade) >= _HIP3_SWING_ENTRY_CUTOFF_MS
    ]
    all_policy_results = build_profit_lock_lifecycle_results(
        cohort_records, asset_records, prospective
    )
    results = [_only_hip3_swing_policy(row) for row in all_policy_results]
    policy = next(
        candidate
        for candidate in POLICIES
        if candidate.policy_id == _HIP3_SWING_POLICY_ID
    )
    report = build_normalized_profit_lock_report(
        results,
        policies=[policy_declaration(policy)],
        contract=_contract(),
        limitations=[
            *_limitations(),
            "the SPCX discovery lifecycle entered before the cutoff and is excluded",
            "only exact HIP-3 Swing/HA provider-symbol mappings are in scope",
            "the policy remains prospective evidence with no automatic promotion",
        ],
    )
    report.update(
        {
            "mode": "hip3_swing_60_30_prospective_observer_v1",
            "scope": "hip3_swing_entries_at_or_after_predeclared_cutoff",
            "policy_origin": "hip3_swing_profit_lock_hypothesis_20260809",
            "hypothesis_id": _HIP3_SWING_HYPOTHESIS_ID,
            "predeclared_at_utc": _HIP3_SWING_PREDECLARED_AT_UTC,
            "entry_cutoff_timestamp_ms": _HIP3_SWING_ENTRY_CUTOFF_MS,
            "strategy_symbol_scope": _hip3_strategy_symbol_scope(),
            "source_matching_lifecycles": len(matching),
            "excluded_predeclaration_lifecycles": len(matching) - len(prospective),
            "prospective_lifecycles": len(prospective),
            "discovery_lifecycle_excluded": True,
            "evidence_state": (
                "prospective_resolutions_observed"
                if prospective
                else "awaiting_post_cutoff_resolution"
            ),
        }
    )
    return report


def build_regime_conditioned_profit_lock_mechanism(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> dict[str, object]:
    """Test frozen locks armed only after five causal opposition decisions."""
    from hypervector.research.cohort_profit_lock_mechanism import (
        build_normalized_regime_conditioned_profit_lock_report,
    )

    results = build_regime_conditioned_lifecycle_results(
        cohort_records, asset_records, reflected_trades
    )
    return build_normalized_regime_conditioned_profit_lock_report(
        results,
        policies=[policy_declaration(policy) for policy in POLICIES],
        contract=_contract(),
        activation_contract=_regime_activation_contract(),
        limitations=[
            *_limitations(),
            "the regime-conditioned mechanism was specified after one live HYPE loss",
            "non-triggering opposition episodes retain the actual exit",
            "this post-hoc report can only define a future frozen observer",
        ],
    )


def build_support_decay_profit_lock_mechanism(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> dict[str, object]:
    """Test frozen locks armed only after five weak-support decisions."""
    from hypervector.research.cohort_profit_lock_mechanism import (
        build_normalized_support_decay_profit_lock_report,
    )

    results = build_support_decay_lifecycle_results(
        cohort_records, asset_records, reflected_trades
    )
    return build_normalized_support_decay_profit_lock_report(
        results,
        policies=[policy_declaration(policy) for policy in POLICIES],
        contract=_contract(),
        activation_contract=_support_decay_activation_contract(),
        limitations=[
            *_limitations(),
            "the support-decay mechanism was specified after an open SOL giveback",
            "this post-hoc report can only define a future frozen observer",
        ],
    )


def _report(
    results: Sequence[Record],
    profile: str,
    run_id: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_profit_lock_challenger_v1",
        "scope": "compatible_profile_history",
        "contract": _contract(),
        "policy_origin": "existing_predeclared_hype_profit_research_v1",
        "policies": [policy_declaration(policy) for policy in POLICIES],
        "summary_by_policy": summaries(results, _POLICY_IDS),
        "by_provider_symbol": grouped_summaries(results, _POLICY_IDS),
        "current_profile": {
            "profile_fingerprint": profile,
            "summary_by_policy": summaries(
                [
                    row
                    for row in results
                    if row["source_profile_fingerprint"] == profile
                ],
                _POLICY_IDS,
            ),
        },
        "current_run": {
            "run_id": run_id,
            "summary_by_policy": summaries(
                [row for row in results if row["source_run_id"] == run_id],
                _POLICY_IDS,
            ),
        },
        "latest_results": list(results[-_LATEST_LIMIT:]),
        "limitations": _limitations(),
    }


def _is_hip3_swing_trade(trade: Record) -> bool:
    strategy = text(trade.get("strategy_id"), "trade strategy")
    symbol = text(trade.get("symbol"), "trade symbol")
    return symbol in _HIP3_SWING_SCOPE.get(strategy, ())


def _entry_timestamp_ms(trade: Record) -> int:
    entry = mapping(trade.get("entry"), "trade entry")
    return nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")


def _only_hip3_swing_policy(result: Record) -> dict[str, object]:
    policies = mapping(result.get("policies"), "profit-lock policies")
    return {
        **result,
        "policies": {
            _HIP3_SWING_POLICY_ID: mapping(
                policies.get(_HIP3_SWING_POLICY_ID),
                _HIP3_SWING_POLICY_ID,
            )
        },
    }


def _hip3_strategy_symbol_scope() -> list[str]:
    return sorted(
        f"{strategy}|{symbol}"
        for strategy, symbols in _HIP3_SWING_SCOPE.items()
        for symbol in symbols
    )


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "portfolio_pnl_claimed": False,
    }


def _regime_activation_contract() -> dict[str, object]:
    return {
        "source": "causal_regime_opposition_persistence_v1",
        "persistence_decisions": _REGIME_PERSISTENCE_DECISIONS,
        "decision_interval_ms": _MINUTE_MS,
        "opposition_threshold": _REGIME_OPPOSITION_THRESHOLD,
        "pre_gate_favorable_excursion_retained": True,
        "same_bar_activation_and_trigger_allowed": False,
    }


def _support_decay_activation_contract() -> dict[str, object]:
    return {
        "source": "causal_regime_support_decay_persistence_v1",
        "persistence_decisions": _REGIME_PERSISTENCE_DECISIONS,
        "decision_interval_ms": _MINUTE_MS,
        "support_decay_threshold": _SUPPORT_DECAY_THRESHOLD,
        "pre_gate_favorable_excursion_retained": True,
        "same_bar_activation_and_trigger_allowed": False,
    }


def _limitations() -> list[str]:
    return [
        "activation and stop updates use prior completed one-minute bars",
        "intrabar paths are unknown and activation bars cannot trigger their new stop",
        "gap-through triggers use the adverse bar open rather than a stale stop price",
        "estimated fills reuse each actual exit fill/reference ratio and fee rate",
        "actual net uses venue closed PnL while counterfactual gross uses recorded average prices",
        "missing holding candles withhold a lifecycle instead of assuming no trigger",
        "overlapping lifecycles are not a counterfactual shared-portfolio equity path",
        "small live samples are mechanism evidence and cannot establish an exit edge",
        "this report cannot gate, size, route, close, or submit a trade",
    ]
