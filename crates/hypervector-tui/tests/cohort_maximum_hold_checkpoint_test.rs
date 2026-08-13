use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;
use serde_json::{Value, json};

fn checkpoint(maximum_hold: Value) -> String {
    json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-04T05:46:00+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"HYPE": "OPEN"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "maximum_hold_decisions": maximum_hold,
            "execution": {"closed_trades": 0, "open_lifecycles": 1, "net_pnl_usd": 0.0},
            "learning": {"evidence_state": "open_trade_evidence"}
        }
    })
    .to_string()
}

fn evidence(balance_gate: bool) -> Value {
    json!({
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "runtime_strategy_changed": false,
            "performance_gate": false,
            "balance_gate": balance_gate
        },
        "summary": {"observed":1,"extended":1,"exited":0,"provider_symbols":1},
        "by_provider_symbol": {
            "hype_breakout_onset_bidirectional_v1|HYPE": {
                "observed":1,"extended":1,"exited":0
            }
        },
        "latest_decisions": [{
            "decision_id": "HYPE:509351044526:soft_maximum_hold",
            "lifecycle_id": "HYPE:509351044526",
            "symbol": "HYPE",
            "strategy_id": "hype_breakout_onset_bidirectional_v1",
            "side": "long",
            "decision_time_ms": 1785812712230_u64,
            "opened_at_ms": 1785783912230_u64,
            "elapsed_ms": 28800000,
            "soft_deadline_timestamp_ms": 1785812712230_u64,
            "hard_deadline_timestamp_ms": 1785870312230_u64,
            "outcome": "extend",
            "exit_reason": null,
            "structure_alignment_score": 0.9167,
            "structure_alignment_threshold": 0.5,
            "provider_evaluation": {"primary_regime":"TREND_UP"},
            "canonical_evaluation": {"state_5m":"TREND_UP"}
        }],
        "extension_outcomes": extension_outcomes(false)
    })
}

fn extension_outcomes(balance_gate: bool) -> Value {
    json!({
        "schema_version": 1,
        "mode": "cohort_maximum_hold_extension_outcomes",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "runtime_strategy_changed": false,
            "automatic_strategy_changes": false,
            "performance_gate": false,
            "balance_gate": balance_gate
        },
        "summary": {
            "bound_extension_lifecycles": 1,
            "resolved": 1,
            "inferred_without_decision_event": 1,
            "better_than_soft_reference": 0,
            "worse_than_soft_reference": 1,
            "unchanged_from_soft_reference": 0,
            "actual_net_pnl_usd": 0.0966,
            "estimated_soft_net_pnl_usd": 0.2482,
            "actual_minus_soft_net_usd": -0.1516
        },
        "by_provider_symbol": {
            "hype_breakout_onset_bidirectional_v1|HYPE": {
                "bound_extension_lifecycles": 1,
                "resolved": 1,
                "inferred_without_decision_event": 1,
                "better_than_soft_reference": 0,
                "worse_than_soft_reference": 1,
                "unchanged_from_soft_reference": 0,
                "actual_net_pnl_usd": 0.0966,
                "estimated_soft_net_pnl_usd": 0.2482,
                "actual_minus_soft_net_usd": -0.1516
            }
        },
        "latest_outcomes": [{
            "status": "resolved",
            "lifecycle_id": "HYPE:509351044526",
            "symbol": "HYPE",
            "strategy_id": "hype_breakout_onset_bidirectional_v1",
            "side": "long",
            "opened_at_ms": 1785793500000_u64,
            "soft_deadline_timestamp_ms": 1785822300000_u64,
            "hard_deadline_timestamp_ms": 1785879900000_u64,
            "actual_exit_timestamp_ms": 1785825622862_u64,
            "extension_duration_ms": 3322862_u64,
            "causal_decision_recorded": false,
            "decision_outcome": null,
            "evidence_basis": "persisted_runtime_plan_plus_resolved_execution",
            "actual_net_pnl_usd": 0.0966,
            "estimated_soft_net_pnl_usd": 0.2482,
            "actual_minus_soft_net_usd": -0.1516
        }],
        "post_soft_trail_challenger": trail_challenger(false),
        "limitations": ["report only"]
    })
}

fn trail_challenger(balance_gate: bool) -> Value {
    json!({
        "schema_version": 1,
        "mode": "cohort_post_soft_trail_challenger_v1",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "runtime_strategy_changed": false,
            "automatic_strategy_changes": false,
            "performance_gate": false,
            "balance_gate": balance_gate
        },
        "policies_giveback_bps": [20.0, 30.0, 40.0],
        "summary_by_giveback_bps": {
            "20": trail_summary(0.14),
            "30": trail_summary(0.16),
            "40": trail_summary(0.0966)
        },
        "latest_results": [{
            "lifecycle_id": "HYPE:509351044526",
            "symbol": "HYPE",
            "strategy_id": "hype_breakout_onset_bidirectional_v1",
            "side": "long",
            "soft_deadline_timestamp_ms": 1785822300000_u64,
            "actual_exit_timestamp_ms": 1785825622862_u64,
            "completed_post_soft_bars": 54,
            "actual_net_pnl_usd": 0.0966,
            "estimated_soft_net_pnl_usd": 0.2482,
            "policies": {
                "20bps": trail_policy(20.0, 0.14),
                "30bps": trail_policy(30.0, 0.16),
                "40bps": {
                    "giveback_bps": 40.0,
                    "status": "not_triggered_before_actual_exit",
                    "trigger_timestamp_ms": null,
                    "trigger_reference_price": null,
                    "trail_price_before_trigger": null,
                    "best_completed_price_before_trigger": null,
                    "estimated_exit_price": 54.153,
                    "estimated_net_pnl_usd": 0.0966,
                    "trail_minus_actual_net_usd": 0.0,
                    "trail_minus_soft_net_usd": -0.1516
                }
            }
        }],
        "limitations": ["report only"]
    })
}

fn trail_summary(estimated: f64) -> Value {
    json!({
        "eligible_extension_lifecycles": 1,
        "triggered": usize::from(estimated != 0.0966),
        "not_triggered": usize::from(estimated == 0.0966),
        "estimated_net_pnl_usd": estimated,
        "actual_net_pnl_usd": 0.0966,
        "estimated_soft_net_pnl_usd": 0.2482,
        "trail_minus_actual_net_usd": estimated - 0.0966,
        "trail_minus_soft_net_usd": estimated - 0.2482
    })
}

fn trail_policy(giveback_bps: f64, estimated: f64) -> Value {
    json!({
        "giveback_bps": giveback_bps,
        "status": "triggered",
        "trigger_timestamp_ms": 1785822500000_u64,
        "trigger_reference_price": 54.20,
        "trail_price_before_trigger": 54.21,
        "best_completed_price_before_trigger": 54.40,
        "estimated_exit_price": 54.19,
        "estimated_net_pnl_usd": estimated,
        "trail_minus_actual_net_usd": estimated - 0.0966,
        "trail_minus_soft_net_usd": estimated - 0.2482
    })
}

#[test]
fn parses_exact_report_only_maximum_hold_decision() {
    let parsed = parse_cohort_checkpoint(&checkpoint(evidence(false))).expect("valid checkpoint");
    let maximum_hold = parsed
        .maximum_hold_decisions
        .expect("maximum-hold evidence");
    let latest = maximum_hold
        .latest_decisions
        .last()
        .expect("latest decision");

    assert_eq!(maximum_hold.observed, 1);
    assert_eq!(maximum_hold.extended, 1);
    assert_eq!(latest.symbol, "HYPE");
    assert_eq!(latest.outcome, "extend");
    assert_eq!(latest.structure_alignment_score, Some(0.9167));
    assert_eq!(latest.hard_deadline_timestamp_ms, Some(1_785_870_312_230));
    let extension = maximum_hold
        .extension_outcomes
        .expect("maximum-hold extension evidence");
    assert_eq!(extension.resolved, 1);
    assert_eq!(extension.worse_than_soft_reference, 1);
    assert_eq!(extension.latest_outcomes[0].symbol, "HYPE");
    assert_eq!(
        extension.latest_outcomes[0].actual_minus_soft_net_usd,
        -0.1516
    );
    let trail = extension
        .post_soft_trail_challenger
        .expect("post-soft trail evidence");
    assert_eq!(trail.summary_by_giveback_bps[&30].triggered, 1);
    assert_eq!(
        trail.latest_results[0].policies[&40].status,
        "not_triggered"
    );
}

#[test]
fn rejects_maximum_hold_evidence_with_a_balance_gate() {
    let error = parse_cohort_checkpoint(&checkpoint(evidence(true))).expect_err("must reject gate");

    assert!(error.contains("maximum-hold contract"), "{error}");
}

#[test]
fn rejects_extension_outcomes_with_a_balance_gate() {
    let mut maximum_hold = evidence(false);
    maximum_hold["extension_outcomes"] = extension_outcomes(true);
    let error = parse_cohort_checkpoint(&checkpoint(maximum_hold)).expect_err("must reject gate");

    assert!(error.contains("maximum-hold extension contract"), "{error}");
}

#[test]
fn rejects_post_soft_trail_with_a_balance_gate() {
    let mut maximum_hold = evidence(false);
    maximum_hold["extension_outcomes"]["post_soft_trail_challenger"] = trail_challenger(true);
    let error = parse_cohort_checkpoint(&checkpoint(maximum_hold)).expect_err("must reject gate");

    assert!(error.contains("post-soft trail contract"), "{error}");
}
