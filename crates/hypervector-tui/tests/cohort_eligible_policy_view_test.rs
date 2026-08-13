use hypervector_tui::backend_cohort_eligible_policy_forward::{
    CohortEligiblePolicyAttempt, CohortEligiblePolicyForward,
};
use hypervector_tui::cohort_research_eligible_policy::summary_texts;

#[test]
fn renders_pending_exact_eth_policy_without_claiming_a_fill() {
    let evidence = CohortEligiblePolicyForward {
        state: "awaiting_exact_policy_resolution".into(),
        symbol: "ETH".into(),
        eligible_signals: 1,
        selected_non_overlapping: 1,
        resolved: 0,
        pending: 1,
        missing_data: 0,
        wins: 0,
        losses: 0,
        total_estimated_net_before_funding_bps: 0.0,
        profit_factor_before_funding: None,
        funding_included: false,
        total_estimated_net_after_funding_bps: None,
        profit_factor_after_funding: None,
        deployable: 1,
        portfolio_attempts: 1,
        latest_portfolio_classification: Some("deployable_flat_entry".into()),
        latest_attempt: Some(CohortEligiblePolicyAttempt {
            source_run_id: "source-run".into(),
            side: "long".into(),
            decision_time_ms: 1_000,
            status: "exit_pending".into(),
            reference_price: 1_896.5,
            observed_candles: Some(53),
            remaining_ms: Some(40_020_000),
            current_gross_return_bps: Some(3.1637),
            current_estimated_net_before_funding_bps: Some(-9.8363),
            current_estimated_net_after_funding_bps: None,
            funding_bps: None,
            mfe_bps: Some(21.62),
            mae_bps: Some(-14.76),
        }),
    };

    let lines = summary_texts(&evidence);

    assert_eq!(lines.len(), 4);
    assert!(lines[0].contains("REPORT ONLY"));
    assert!(lines[0].contains("60 BPS STOP / 12H HOLD / 13 BPS FRICTION"));
    assert!(lines[1].contains("PENDING 1"));
    assert!(lines[1].contains("PORTFOLIO FIT 1/1"));
    assert!(lines[2].contains("MARK +3.2 BPS GROSS / -9.8 BPS BEFORE FUNDING"));
    assert!(lines[3].contains("FILL NOT PROVEN"));
}

#[test]
fn renders_official_funding_separately_from_modeled_friction() {
    let evidence = CohortEligiblePolicyForward {
        state: "awaiting_exact_policy_resolution".into(),
        symbol: "ETH".into(),
        eligible_signals: 1,
        selected_non_overlapping: 1,
        resolved: 0,
        pending: 1,
        missing_data: 0,
        wins: 0,
        losses: 0,
        total_estimated_net_before_funding_bps: 0.0,
        profit_factor_before_funding: None,
        funding_included: true,
        total_estimated_net_after_funding_bps: None,
        profit_factor_after_funding: None,
        deployable: 1,
        portfolio_attempts: 1,
        latest_portfolio_classification: Some("deployable_flat_entry".into()),
        latest_attempt: Some(CohortEligiblePolicyAttempt {
            source_run_id: "source-run".into(),
            side: "long".into(),
            decision_time_ms: 1_000,
            status: "exit_pending".into(),
            reference_price: 1_896.5,
            observed_candles: Some(53),
            remaining_ms: Some(40_020_000),
            current_gross_return_bps: Some(3.1637),
            current_estimated_net_before_funding_bps: Some(-9.8363),
            current_estimated_net_after_funding_bps: Some(-10.3363),
            funding_bps: Some(-0.5),
            mfe_bps: Some(21.62),
            mae_bps: Some(-14.76),
        }),
    };

    let lines = summary_texts(&evidence);

    assert!(lines[0].contains("OFFICIAL FUNDING"));
    assert!(lines[2].contains("BEFORE -9.8"));
    assert!(lines[2].contains("FUND -0.5"));
    assert!(lines[2].contains("NET -10.3 BPS"));
}
