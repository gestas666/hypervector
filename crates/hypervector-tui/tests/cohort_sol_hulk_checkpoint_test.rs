#![allow(dead_code)]

use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;

#[test]
fn projects_report_only_sol_hulk_expansion_observer() {
    let mut value = checkpoint(matrix_contract());
    let mut observer = forward_challenger();
    observer["state"] = "awaiting_fresh_post_cutoff_candidate".into();
    observer["generated_at_utc"] = "2026-08-07T05:05:53+00:00".into();
    observer["contract"]["cutoff_time_ms"] = 1_786_078_920_000_u64.into();
    observer["contract"]["cutoff_utc"] = "2026-08-07T05:02:00+00:00".into();
    observer["contract"]["source_signal_authority"] = "observe_only".into();
    observer["contract"]["execution"]["strategy_id"] =
        "hulk_expansion_bidirectional_tuned_v2".into();
    observer["contract"]["execution"]["symbol"] = "SOL".into();
    observer["contract"]["execution"]["blocker"] = "expansion_trigger_not_present".into();
    observer["contract"]["execution"]["opi_cohort"] = "all".into();
    observer["contract"]["execution"]["minimum_available_time_ms"] = 1_786_078_920_000_u64.into();
    observer["contract"]["execution"]["notional_usd"] = 75.0.into();
    observer["contract"]["execution"]["stop_proxy_bps"] = 75.0.into();
    observer["coverage"]["exact_candidates"] = 0.into();
    observer["coverage"]["selected_non_overlapping"] = 0.into();
    observer["coverage"]["resolved_executions"] = 0.into();
    observer["portfolio_journal"]["contract"]["source_strategy_id"] =
        "hulk_expansion_bidirectional_tuned_v2".into();
    observer["portfolio_journal"]["contract"]["candidate_strategy_id"] =
        "sol_hulk_expansion_trigger_relaxed_fixed60_bidirectional_v1".into();
    observer["portfolio_journal"]["contract"]["symbol"] = "SOL".into();
    observer["portfolio_journal"]["state"] = "awaiting_attempts".into();
    observer["portfolio_journal"]["summary"] = empty_portfolio_summary();
    observer["portfolio_journal"]["latest_attempts"] = serde_json::json!([]);
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([observer]);

    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("SOL Hulk observer");
    let matrix = parsed.execution_opportunity_matrix.expect("matrix");
    let challenger = &matrix.supplemental_forward_challengers[0];

    assert_eq!(challenger.execution_contract.symbol, "SOL");
    assert_eq!(challenger.execution_contract.opi_cohort, "all");
    assert_eq!(challenger.execution_contract.stop_proxy_bps, 75.0);
}

fn empty_portfolio_summary() -> serde_json::Value {
    serde_json::json!({
        "attempts": 0,
        "deployable": 0,
        "deployable_resolved": 0,
        "deployable_wins": 0,
        "deployable_losses": 0,
        "deployable_total_net_return_bps": 0.0,
        "deployable_profit_factor": null,
        "deployable_largest_abs_contribution_fraction": null,
        "existing_symbol_position": 0,
        "portfolio_capacity": 0,
        "same_cycle_symbol_action": 0,
        "portfolio_state_unavailable": 0,
        "resolved": 0,
        "pending": 0
    })
}

include!("support/cohort_execution_opportunity_matrix_checkpoint_fixtures.rs");
