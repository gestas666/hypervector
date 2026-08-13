#[test]
fn projects_report_only_execution_opportunity_matrix() {
    let mut checkpoint = checkpoint(matrix_contract());
    checkpoint["audit"]["execution_opportunity_matrix"]["checkpoint_provenance"] = serde_json::json!({
        "relationship": "historical_prior_run",
        "checkpoint_run_id": "bidirectional-live-current",
        "checkpoint_first_observed_at_utc": "2026-08-06T00:34:14+00:00",
        "evidence_run_id": "bidirectional-live-prior",
        "evidence_config_path": "configs/prior.toml",
        "matrix_updated_at_utc": "2026-08-05T21:59:22+00:00"
    });
    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("valid matrix");
    let matrix = parsed
        .execution_opportunity_matrix
        .expect("matrix projection");
    let provenance = matrix.provenance.as_ref().expect("matrix provenance");
    assert_eq!(provenance.relationship, "historical_prior_run");
    assert_eq!(provenance.checkpoint_run_id, "bidirectional-live-current");
    assert_eq!(
        provenance.evidence_run_id.as_deref(),
        Some("bidirectional-live-prior")
    );
    assert_eq!(
        provenance.evidence_config_path.as_deref(),
        Some("configs/prior.toml")
    );
    assert_eq!(matrix.hypotheses, 1);
    assert_eq!(matrix.comparisons, 3);
    let scope = matrix.scope.as_ref().expect("matrix hypothesis scope");
    assert_eq!(scope.observed_hypotheses, 3);
    assert_eq!(scope.executable_hypotheses, 1);
    assert_eq!(scope.excluded_non_executable_hypotheses, 2);
    assert_eq!(matrix.results.len(), 3);
    let broadest = matrix.broadest_all_cohort().expect("all-cohort row");
    assert_eq!(broadest.symbol, "HYPE");
    assert_eq!(broadest.resolved, 9);
    assert_eq!(broadest.long_resolved, 9);
    assert_eq!(broadest.short_resolved, 0);
    let forward = matrix.forward_challenger.expect("forward challenger");
    assert_eq!(forward.state, "awaiting_executable_resolution");
    assert_eq!(forward.exact_candidates, 31);
    assert_eq!(forward.selected_non_overlapping, 1);
    assert_eq!(forward.resolved, 0);
    let portfolio = forward.portfolio_journal.expect("portfolio journal");
    assert_eq!(portfolio.attempts, 1);
    assert_eq!(portfolio.deployable, 1);
    assert_eq!(portfolio.pending, 1);
    let latest = portfolio.latest_attempt.expect("latest attempt");
    assert_eq!(latest.classification, "deployable_flat_entry");
    assert_eq!(latest.current_estimated_net_return_bps, Some(31.0));
    assert_eq!(latest.mfe_bps, Some(45.0));
    assert_eq!(latest.mae_bps, Some(-2.0));
    assert_eq!(latest.remaining_ms, Some(2_700_000));
    assert_eq!(latest.state_5m.as_deref(), Some("TREND_DOWN"));
    assert_eq!(latest.structural_direction.as_deref(), Some("long"));
    assert_eq!(latest.breakout_volume_ratio, Some(0.14));
    let projection = format!("{latest:?}");
    for expected in [
        "primary_regime: Some(\"TREND_DOWN\")",
        "state_1m: Some(\"RANGE\")",
        "context_15m: Some(\"RANGE\")",
    ] {
        assert!(
            projection.contains(expected),
            "missing {expected}: {projection}"
        );
    }
}

#[test]
fn rejects_matrix_whose_hypothesis_scope_does_not_reconcile() {
    let mut checkpoint = checkpoint(matrix_contract());
    checkpoint["audit"]["execution_opportunity_matrix"]["scope"]["executable_hypotheses"] =
        2.into();

    let error = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect_err("hypothesis scope must reconcile");

    assert!(error.contains("hypothesis scope"));
}

#[test]
fn rejects_matrix_that_claims_execution_authority() {
    let mut contract = matrix_contract();
    contract["execution_authority"] = "hyperliquid_mainnet".into();
    let checkpoint = checkpoint(contract);
    let error = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect_err("execution authority must fail closed");
    assert!(error.contains("opportunity matrix contract"));
}

#[test]
fn rejects_matrix_whose_side_totals_do_not_reconcile() {
    let mut checkpoint = checkpoint(matrix_contract());
    checkpoint["audit"]["execution_opportunity_matrix"]["results"][0]["long"]["total_net_return_bps"] =
        100.0.into();
    checkpoint["audit"]["execution_opportunity_matrix"]["results"][0]["long"]["mean_net_return_bps"] =
        12.5.into();
    let error =
        parse_cohort_checkpoint(&checkpoint.to_string()).expect_err("side totals must reconcile");
    assert!(error.contains("opportunity comparison"));
}

#[test]
fn projects_latest_resolved_forward_path_with_friction_and_excursions() {
    let mut value = checkpoint(matrix_contract());
    value["audit"]["execution_opportunity_matrix"]["forward_challenger"] =
        resolved_forward_challenger();
    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("resolved forward path");
    let forward = parsed
        .execution_opportunity_matrix
        .expect("matrix")
        .forward_challenger
        .expect("forward challenger");
    let latest = forward.latest_execution.expect("latest execution");
    assert_eq!(forward.resolved, 1);
    assert_eq!(latest.source_run_id, "bidirectional-live-a");
    assert_eq!(latest.side, "long");
    assert_eq!(latest.net_return_bps, 19.966);
    assert_eq!(latest.mfe_bps, 75.384);
    assert_eq!(latest.mae_bps, -23.682);
    assert_eq!(latest.exit_reason, "fixed_horizon");
    let context = forward
        .entry_context_summary
        .expect("forward regime context");
    assert_eq!(context.state_5m_observed, 1);
    assert_eq!(context.state_5m_missing, 0);
    assert_eq!(context.neutral.resolved, 1);
    assert_eq!(context.neutral.total_net_return_bps, 19.966);
    let context_15m = forward
        .context_15m_summary
        .expect("forward fifteen-minute context");
    assert_eq!(context_15m.context_15m_observed, 1);
    assert_eq!(context_15m.context_15m_missing, 0);
    assert_eq!(context_15m.aligned.resolved, 1);
    assert_eq!(context_15m.aligned.total_net_return_bps, 19.966);
    let portfolio = forward.portfolio_journal.expect("portfolio journal");
    assert_eq!(portfolio.attempts, 2);
    assert_eq!(portfolio.deployable, 2);
    assert_eq!(portfolio.resolved, 1);
    assert_eq!(portfolio.pending, 1);
}

#[test]
fn projects_deployable_economics_separately_from_all_paths() {
    let mut value = checkpoint(matrix_contract());
    let mut forward = resolved_forward_challenger();
    let summary = &mut forward["portfolio_journal"]["summary"];
    summary["deployable_resolved"] = 1.into();
    summary["deployable_wins"] = 1.into();
    summary["deployable_losses"] = 0.into();
    summary["deployable_total_net_return_bps"] = 19.966.into();
    summary["deployable_profit_factor"] = serde_json::Value::Null;
    summary["deployable_largest_abs_contribution_fraction"] = 1.0.into();
    value["audit"]["execution_opportunity_matrix"]["forward_challenger"] = forward;

    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("deployable economics");
    let portfolio = parsed
        .execution_opportunity_matrix
        .expect("matrix")
        .forward_challenger
        .expect("forward")
        .portfolio_journal
        .expect("portfolio journal");

    let projection = format!("{portfolio:?}");
    assert!(
        projection.contains("deployable_total_net_return_bps: Some(19.966)"),
        "{projection}"
    );
}

#[test]
fn rejects_deployable_economics_that_do_not_reconcile_to_attempts() {
    let mut value = checkpoint(matrix_contract());
    let summary = &mut value["audit"]["execution_opportunity_matrix"]["forward_challenger"]["portfolio_journal"]
        ["summary"];
    summary["deployable_resolved"] = 0.into();
    summary["deployable_wins"] = 0.into();
    summary["deployable_losses"] = 0.into();
    summary["deployable_total_net_return_bps"] = 999.0.into();
    summary["deployable_profit_factor"] = serde_json::Value::Null;
    summary["deployable_largest_abs_contribution_fraction"] = serde_json::Value::Null;

    let error = parse_cohort_checkpoint(&value.to_string())
        .expect_err("deployable economics must reconcile");

    assert!(error.contains("candidate portfolio journal"));
}

#[test]
fn accepts_the_independently_identified_target20_candidate_journal() {
    let mut value = checkpoint(matrix_contract());
    value["audit"]["execution_opportunity_matrix"]["forward_challenger"] =
        target20_resolved_forward_challenger();
    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("target20 journal");
    let forward = parsed
        .execution_opportunity_matrix
        .expect("matrix")
        .forward_challenger
        .expect("target20 challenger");
    assert_eq!(forward.target_proxy_bps, Some(20.0));
    let payoff = forward.payoff_geometry.expect("target payoff geometry");
    assert_eq!(payoff.estimated_target_net_bps, 11.36);
    assert_eq!(payoff.estimated_stop_net_bps, -88.64);
    assert_eq!(payoff.break_even_target_rate_pct, Some(88.64));
    assert_eq!(
        forward.latest_execution.expect("target path").exit_reason,
        "target_proxy"
    );
}

#[test]
fn rejects_forward_portfolio_journal_that_claims_live_pnl() {
    let mut value = checkpoint(matrix_contract());
    value["audit"]["execution_opportunity_matrix"]["forward_challenger"]["portfolio_journal"]["contract"]
        ["portfolio_pnl_claimed"] = true.into();

    let error = parse_cohort_checkpoint(&value.to_string())
        .expect_err("candidate journal must remain non-authoritative");

    assert!(error.contains("candidate portfolio journal"));
}

#[test]
fn projects_a_distinct_btc_supplemental_forward_observer() {
    let mut value = checkpoint(matrix_contract());
    let mut btc = forward_challenger();
    btc["contract"]["execution"]["strategy_id"] = "range_onset_bidirectional_v1".into();
    btc["contract"]["execution"]["symbol"] = "BTC".into();
    btc["contract"]["execution"]["blocker"] = "awaiting_hourly_sma_cross".into();
    btc["portfolio_journal"]["contract"]["source_strategy_id"] =
        "range_onset_bidirectional_v1".into();
    btc["portfolio_journal"]["contract"]["candidate_strategy_id"] =
        "btc_structural_continuation_fixed60_bidirectional_v1".into();
    btc["portfolio_journal"]["contract"]["symbol"] = "BTC".into();
    btc["portfolio_journal"]["latest_attempts"][0]["entry_features"] =
        serde_json::json!({"structural_direction": "long"});
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([btc]);

    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("two forward observers");
    let matrix = parsed.execution_opportunity_matrix.expect("matrix");

    assert_eq!(matrix.supplemental_forward_challengers.len(), 1);
    let journal = matrix.supplemental_forward_challengers[0]
        .portfolio_journal
        .as_ref()
        .expect("BTC journal");
    assert_eq!(
        journal.candidate_strategy_id,
        "btc_structural_continuation_fixed60_bidirectional_v1"
    );
    assert_eq!(journal.symbol, "BTC");
}

#[test]
fn projects_btc_hulk_money_flow_forward_observer() {
    let mut value = checkpoint(matrix_contract());
    let mut btc = forward_challenger();
    btc["contract"]["execution"]["strategy_id"] = "hulk_expansion_bidirectional_tuned_v2".into();
    btc["contract"]["execution"]["symbol"] = "BTC".into();
    btc["contract"]["execution"]["blocker"] = "money_flow_not_aligned".into();
    btc["portfolio_journal"]["contract"]["source_strategy_id"] =
        "hulk_expansion_bidirectional_tuned_v2".into();
    btc["portfolio_journal"]["contract"]["candidate_strategy_id"] =
        "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1".into();
    btc["portfolio_journal"]["contract"]["symbol"] = "BTC".into();
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([btc]);

    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("BTC Hulk observer");
    let matrix = parsed.execution_opportunity_matrix.expect("matrix");
    let journal = matrix.supplemental_forward_challengers[0]
        .portfolio_journal
        .as_ref()
        .expect("BTC Hulk journal");

    assert_eq!(journal.symbol, "BTC");
    assert_eq!(
        journal.candidate_strategy_id,
        "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1"
    );
}

#[test]
fn projects_distinct_hype_supplemental_observers() {
    let mut value = checkpoint(matrix_contract());
    let mut hulk = forward_challenger();
    hulk["contract"]["execution"]["strategy_id"] = "hulk_expansion_bidirectional_tuned_v2".into();
    hulk["contract"]["execution"]["blocker"] = "squeeze_not_armed".into();
    hulk["portfolio_journal"]["contract"]["source_strategy_id"] =
        "hulk_expansion_bidirectional_tuned_v2".into();
    hulk["portfolio_journal"]["contract"]["candidate_strategy_id"] =
        "hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1".into();
    let mut range = hulk.clone();
    range["contract"]["execution"]["strategy_id"] = "range_onset_bidirectional_v1".into();
    range["contract"]["execution"]["blocker"] = "awaiting_hourly_sma_cross".into();
    range["contract"]["execution"]["opi_cohort"] = "opposed".into();
    range["portfolio_journal"]["contract"]["source_strategy_id"] =
        "range_onset_bidirectional_v1".into();
    range["portfolio_journal"]["contract"]["candidate_strategy_id"] =
        "hype_range_absorption_fixed60_bidirectional_v1".into();
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([hulk, range]);

    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("HYPE observers");
    assert_eq!(parsed.trade_reflections.len(), 0);
    let matrix = parsed.execution_opportunity_matrix.expect("matrix");
    assert_eq!(matrix.supplemental_forward_challengers.len(), 2);
}
