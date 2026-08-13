"""Pre-registered causal entry and exit challengers for exact live v39 evidence."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.research.v39_forward_evidence_contract import (
    PROFILE_FINGERPRINT,
    PROFILE_ID,
)

Record = Mapping[str, object]
_EXPLORATORY_CLOSED_LIFECYCLES = 50
_PROMOTION_INDEPENDENT_EPOCHS = 200


def build_v39_causal_challenger_program(
    forward: Record,
    checkpoint: Record,
) -> dict[str, object]:
    """Describe two fixed report-only experiments and present sample readiness."""
    _require_exact_v39_report(forward)
    sample = _current_exact_sample(forward, checkpoint)
    return {
        "schema_version": "v39_causal_challenger_program_v1",
        "mode": "pre_registered_report_only_challengers",
        "contract": _contract(),
        "current_exact_sample": sample,
        "experiments": {
            "entry_microstructure_ranker": _entry_experiment(),
            "exit_momentum_support_decay": _exit_experiment(),
        },
        "assessment": _assessment(sample),
        "limitations": _limitations(),
    }


def _entry_experiment() -> dict[str, object]:
    return {
        "experiment_id": "v39_entry_microstructure_ranker_v1",
        "hypothesis": (
            "decision-time liquidity support ranks existing eligible signals after "
            "friction without replacing their direction or eligibility"
        ),
        "stage": "capture_and_join_required_before_fit",
        "scope": "all_v39_routes_with_exact_causal_l2_and_completed_bar_features",
        "action": "rank_and_annotate_only",
        "features": _entry_features(),
        "model": _entry_model(),
        "validation": _entry_validation(),
    }


def _entry_features() -> list[dict[str, object]]:
    return [
        {
            "name": "side_aligned_opi_depth10",
            "timestamp": "latest_recv_at_or_before_routing_publication_max_age_30s",
        },
        {
            "name": "log_spread_vs_trailing_24h_median",
            "timestamp": "same_causal_l2_snapshot_and_prior_only_baseline",
        },
        {
            "name": "bbwp_5m_fraction",
            "timestamp": "last_completed_5m_bar_before_entry_decision",
        },
        {
            "name": "log1p_volume_ratio_20m",
            "timestamp": "last_completed_provider_bar_before_entry_decision",
        },
    ]


def _entry_model() -> dict[str, object]:
    return {
        "family": "ridge_regression_l2",
        "regularization": "alpha_1_fixed_no_parameter_sweep",
        "training_features": "expanding_window_standardized_from_prior_rows_only",
        "target": "30m_directional_close_return_less_frozen_route_friction_bps",
        "output": "within_route_continuous_quality_rank",
        "runtime_size_mapping": None,
    }


def _entry_validation() -> dict[str, object]:
    return {
        "split": "expanding_walk_forward_grouped_by_nonoverlapping_30m_epoch",
        "purge": "maximum_label_overlap",
        "embargo": "24h_maximum_strategy_hold",
        "primary_metrics": [
            "out_of_sample_spearman_ic",
            "after_friction_net_return_by_rank_bucket",
            "profit_factor_excluding_largest_winner",
            "maximum_drawdown",
            "long_short_and_regime_slices",
        ],
        "exploratory_fit_minimum_closed_lifecycles": _EXPLORATORY_CLOSED_LIFECYCLES,
        "promotion_claim_minimum_independent_epochs": _PROMOTION_INDEPENDENT_EPOCHS,
        "shuffle_falsifier": "timestamp_shuffling_must_collapse_out_of_sample_ic",
    }


def _exit_experiment() -> dict[str, object]:
    return {
        "experiment_id": "v39_exit_momentum_support_decay_v1",
        "hypothesis": (
            "completed-bar momentum support decay identifies continuation failure "
            "more selectively than generic profit locks or loss thresholds"
        ),
        "stage": "prospective_lifecycle_annotation_only",
        "scope": "core_symbols_with_canonical_regime_telemetry",
        "action": "label_and_annotate_only",
        "features": _exit_features(),
        "model": _exit_model(),
        "validation": _exit_validation(),
    }


def _exit_features() -> list[dict[str, object]]:
    timestamp = "each_completed_1m_canonical_decision_while_position_open"
    return [
        {"name": "directional_rsi_level", "timestamp": timestamp},
        {"name": "directional_rsi_velocity_3", "timestamp": timestamp},
        {"name": "directional_tqi_level_and_velocity_3", "timestamp": timestamp},
        {"name": "directional_trend_slope_bps", "timestamp": timestamp},
        {"name": "harsi_and_5m_bias_alignment", "timestamp": timestamp},
    ]


def _exit_model() -> dict[str, object]:
    return {
        "family": "logistic_regression_l2",
        "regularization": "c_1_fixed_no_parameter_sweep",
        "training_features": "prior_completed_lifecycles_only",
        "target": "next_15m_continuation_clears_frozen_route_friction",
        "output": "continuous_continuation_probability_and_decay_label",
        "decay_label": "probability_below_0.5_after_three_completed_decisions",
        "runtime_exit_mapping": None,
    }


def _exit_validation() -> dict[str, object]:
    return {
        "split": "walk_forward_grouped_by_lifecycle",
        "purge": "all_overlapping_within_lifecycle_observations",
        "embargo": "24h_maximum_strategy_hold",
        "primary_metrics": [
            "paired_after_friction_delta_vs_actual_exit",
            "median_net_return_delta",
            "profit_factor_excluding_largest_winner",
            "taker_exit_count_and_cost",
            "long_short_and_regime_slices",
        ],
        "exploratory_fit_minimum_closed_lifecycles": _EXPLORATORY_CLOSED_LIFECYCLES,
        "promotion_claim_minimum_closed_lifecycles": 150,
        "rejection": "reject_if_cost_or_outlier_sensitivity_erases_paired_improvement",
    }


def _current_exact_sample(forward: Record, checkpoint: Record) -> dict[str, object]:
    summary = _mapping(forward.get("summary"), "forward summary")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    opened = _mapping(audit.get("open_trade_reflections"), "open reflections")
    canonical = _mapping(
        audit.get("canonical_regime_telemetry"), "canonical regime telemetry"
    )
    by_symbol = _mapping(canonical.get("by_symbol"), "canonical regime symbols")
    return {
        "eligible_evaluations": _count(summary.get("eligible_evaluations"), "eligible"),
        "resolved_closed_lifecycles": _count(summary.get("closed_trades"), "closes"),
        "provisional_open_lifecycles": len(_records(opened.get("trades"))),
        "canonical_regime_symbols": sorted(by_symbol),
    }


def _assessment(sample: Record) -> dict[str, object]:
    closes = _count(sample.get("resolved_closed_lifecycles"), "sample closes")
    return {
        "model_fit_now": closes >= _EXPLORATORY_CLOSED_LIFECYCLES,
        "reason": (
            "preregistered_fit_permitted_after_independence_audit"
            if closes >= _EXPLORATORY_CLOSED_LIFECYCLES
            else "resolved_lifecycle_sample_is_sparse"
        ),
        "next_evidence_action": (
            "continue_exact_feature_and_lifecycle_capture_without_runtime_changes"
        ),
    }


def _require_exact_v39_report(forward: Record) -> None:
    contract = _mapping(forward.get("contract"), "forward contract")
    if not (
        contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("performance_gate") is False
    ):
        raise ValueError("v39 challenger source must be authority-none and ungated")
    source = _mapping(forward.get("source"), "forward source")
    if not (
        source.get("profile_id") == PROFILE_ID
        and source.get("profile_fingerprint") == PROFILE_FINGERPRINT
    ):
        raise ValueError("v39 profile identity does not match the frozen contract")


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "current_v39_strategy_signals_authoritative": True,
        "entry_gate": False,
        "exit_authority": False,
        "position_sizing_authority": False,
        "automatic_retuning": False,
        "automatic_promotion": False,
        "performance_thresholds_are_execution_gates": False,
    }


def _limitations() -> list[str]:
    return [
        "current resolved v39 lifecycle sample is insufficient for model fitting",
        "eligible-event L2 features still require exact decision-time joins",
        "HIP-3 routes lack canonical regime telemetry for the exit challenger",
        "overlapping observations must be grouped and purged by lifecycle",
        "research thresholds are evidence labels and cannot alter live execution",
    ]


def _records(value: object) -> list[Record]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError("open reflections must be an array of objects")
    return value


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
