use super::{
    context_15m_text, deployable_performance_text, detail_lines, entry_context_text,
    forward_contract_text, forward_contract_timing_text, hypothesis_scope_text,
    mechanism_performance_text, payoff_geometry_text, pending_entry_context_line,
    portfolio_summary_line,
};
use crate::backend_cohort_checkpoint::CohortCheckpointTelemetry;
use crate::backend_cohort_execution_opportunity_matrix::{
    CohortExecutionOpportunityComparison, CohortExecutionOpportunityMatrix,
    CohortExecutionOpportunityScope, CohortOpportunityMatrixProvenance,
};
use crate::backend_cohort_forward_challenger::{
    CohortForwardExecutionContract, CohortForwardOneBlockerChallenger,
};
use crate::cohort_observer_evidence::CohortObserverProviderEvidence;
use crate::cohort_opportunity_matrix_provenance::matrix_provenance_text;
use crate::cohort_research_forward_format::{
    detail_title as forward_detail_title, title as forward_title,
};

#[test]
fn historical_matrix_has_an_unambiguous_run_label() {
    let provenance = CohortOpportunityMatrixProvenance {
        relationship: "historical_prior_run".into(),
        checkpoint_run_id: "bidirectional-live-current".into(),
        checkpoint_first_observed_at_utc: "2026-08-06T00:34:14+00:00".into(),
        evidence_run_id: Some("bidirectional-live-prior".into()),
        evidence_config_path: Some("configs/prior.toml".into()),
        matrix_updated_at_utc: Some("2026-08-05T21:59:22+00:00".into()),
    };

    assert_eq!(
        matrix_provenance_text(Some(&provenance)),
        "HISTORICAL PRIOR RUN bidirectional-live-prior"
    );
    assert_eq!(matrix_provenance_text(None), "PROVENANCE UNAVAILABLE");
}

#[test]
fn frozen_forward_contract_is_operator_visible() {
    let contract = aligned_contract();

    assert_eq!(
        forward_contract_text(&contract),
        "CONTRACT HYPE // OPI ALIGNED // $75 // FEE 4.32bps // STOP 80bps // TARGET NONE // HOLD 60M // SPACE 15M"
    );
    assert_eq!(
        forward_contract_timing_text(&contract),
        "TIMING CTX<=30s // ENTRY<=60s // EXIT<=30s // CUTOFF 2026-08-06T22:08:00+00:00 // AUTH NONE"
    );
}

#[test]
fn research_detail_lines_render_the_frozen_contract() {
    let contract = aligned_contract();
    let journal = portfolio_journal();
    let forward = CohortForwardOneBlockerChallenger {
        state: "awaiting_executable_resolution".into(),
        generated_at_utc: "2026-08-06T22:09:00+00:00".into(),
        execution_contract: contract,
        target_proxy_bps: None,
        payoff_geometry: None,
        exact_candidates: 1,
        selected_non_overlapping: 1,
        resolved: 0,
        wins: 0,
        losses: 0,
        total_net_return_bps: 0.0,
        profit_factor: None,
        largest_abs_contribution_fraction: None,
        stop_proxy_crosses: 0,
        long_resolved: 0,
        short_resolved: 0,
        entry_context_summary: None,
        context_15m_summary: None,
        latest_execution: None,
        portfolio_journal: Some(journal),
    };
    let mut app = App::new("HYPE".into(), "1m".into(), Vec::new(), false, false);
    app.backend.cohort_checkpoint = CohortCheckpointTelemetry {
        execution_opportunity_matrix: Some(matrix_with_forward(forward)),
        ..CohortCheckpointTelemetry::default()
    };
    let provider = provider_row();

    let rendered = detail_lines(&provider, &app)
        .iter()
        .flat_map(|line| line.spans.iter())
        .map(|span| span.content.as_ref())
        .collect::<Vec<_>>()
        .join("\n");

    assert!(
        rendered.contains("CONTRACT HYPE // OPI ALIGNED // $75"),
        "{rendered}"
    );
    assert!(rendered.contains("FEE 4.32bps // STOP 80bps"), "{rendered}");
    assert!(
        rendered.contains("TIMING CTX<=30s // ENTRY<=60s // EXIT<=30s"),
        "{rendered}"
    );
    assert!(rendered.contains("AUTH NONE"), "{rendered}");
}

fn aligned_contract() -> CohortForwardExecutionContract {
    CohortForwardExecutionContract {
        strategy_id: "source".into(),
        symbol: "HYPE".into(),
        blocker: "order_book_imbalance_below_minimum".into(),
        opi_cohort: "aligned".into(),
        horizon_minutes: 60,
        maximum_context_age_ms: Some(30_000),
        maximum_entry_delay_ms: Some(60_000),
        maximum_exit_delay_ms: Some(30_000),
        minimum_entry_spacing_minutes: 15,
        notional_usd: 75.0,
        taker_fee_rate: 0.000432,
        stop_proxy_bps: 80.0,
        target_proxy_bps: None,
        cutoff_time_ms: 1_786_054_080_000,
        cutoff_utc: "2026-08-06T22:08:00+00:00".into(),
        minimum_available_time_ms: 1_786_054_080_000,
        execution_authority: "none".into(),
    }
}

fn matrix_with_forward(
    forward: CohortForwardOneBlockerChallenger,
) -> CohortExecutionOpportunityMatrix {
    CohortExecutionOpportunityMatrix {
        provenance: None,
        hypotheses: 1,
        comparisons: 1,
        scope: None,
        results: vec![CohortExecutionOpportunityComparison {
            strategy_id: "source".into(),
            symbol: "HYPE".into(),
            blocker: "order_book_imbalance_below_minimum".into(),
            opi_cohort: "aligned".into(),
            resolved: 0,
            wins: 0,
            losses: 0,
            total_net_return_bps: 0.0,
            mean_net_return_bps: None,
            profit_factor: None,
            largest_abs_contribution_fraction: None,
            stop_proxy_crosses: 0,
            long_resolved: 0,
            short_resolved: 0,
        }],
        forward_challenger: Some(forward),
        supplemental_forward_challengers: Vec::new(),
    }
}

fn provider_row() -> CohortObserverProviderEvidence {
    CohortObserverProviderEvidence {
        strategy_id: "source".into(),
        symbol: "HYPE".into(),
        research_state: None,
        confidence: None,
        historical_cadence: None,
        historical_summary: None,
        evidence_source: None,
        directional_research: Default::default(),
        forward_assessment: None,
        execution_performance_scope: None,
        execution_performance: None,
        execution_performance_by_side: Default::default(),
        repeatability_evidence: None,
        latest_side: None,
        readiness_fraction: None,
        latest_reason: None,
        latest_blockers: Vec::new(),
        readiness_evaluations: 0,
        eligible_signals: 0,
        paths: Default::default(),
        eligible_paths: Default::default(),
        readiness_paths: Default::default(),
        one_blocker_near_misses: None,
        orderbook_opportunity: None,
    }
}

#[test]
fn standalone_candidate_result_is_labeled_as_mechanism_evidence() {
    assert_eq!(
        mechanism_performance_text(7, 5, 2, 135.8623, Some(2.6051)),
        "MECH N7 5/2 NET +135.9bps PF 2.61"
    );
}

#[test]
fn zero_sample_mechanism_does_not_claim_no_losses() {
    assert_eq!(
        mechanism_performance_text(0, 0, 0, 0.0, None),
        "MECH N0 0/0 NET +0.0bps PF N/A"
    );
}

#[test]
fn executable_matrix_scope_is_explicit_and_compact() {
    let scope = CohortExecutionOpportunityScope {
        observed_hypotheses: 18,
        executable_hypotheses: 2,
        excluded_non_executable_hypotheses: 16,
    };

    assert_eq!(
        hypothesis_scope_text(Some(&scope), 2),
        "EXEC HYP 2/18 // OBSERVE-ONLY 16"
    );
    assert_eq!(
        hypothesis_scope_text(None, 2),
        "EXEC HYP 2 // SCOPE UNAVAILABLE"
    );
}
use crate::App;
use crate::backend_cohort_forward_challenger::{
    CohortCandidatePortfolioAttempt, CohortCandidatePortfolioJournal, CohortForwardPayoffGeometry,
};
use crate::backend_cohort_forward_entry_context::{
    CohortForwardContext15mSummary, CohortForwardEntryContextSummary, CohortForwardRegimeBucket,
};

#[test]
fn target_first_challenger_exposes_fee_adjusted_payoff_geometry() {
    let geometry = CohortForwardPayoffGeometry {
        estimated_round_trip_fee_bps: 8.64,
        estimated_target_net_bps: 11.36,
        estimated_stop_net_bps: -88.64,
        break_even_target_rate_pct: Some(88.64),
        fixed_horizon_changes_realized_distribution: true,
    };

    assert_eq!(
        payoff_geometry_text(&geometry),
        "BRACKET NET T+11.4 / S-88.6bps // B/E TARGET 88.6% // 60M FALLBACK CHANGES OUTCOMES"
    );
}

#[test]
fn forward_entry_context_is_compact_and_directional() {
    let value = CohortForwardEntryContextSummary {
        state_5m_observed: 2,
        state_5m_missing: 0,
        aligned: CohortForwardRegimeBucket::default(),
        opposed: CohortForwardRegimeBucket {
            resolved: 1,
            total_net_return_bps: -20.0,
            ..CohortForwardRegimeBucket::default()
        },
        neutral: CohortForwardRegimeBucket {
            resolved: 1,
            total_net_return_bps: 14.0,
            ..CohortForwardRegimeBucket::default()
        },
        unavailable: CohortForwardRegimeBucket::default(),
    };

    assert_eq!(
        entry_context_text(&value),
        "5M ENTRY CONTEXT OBS 2/2 // ALIGNED N0 +0.0 // OPPOSED N1 -20.0 // NEUTRAL N1 +14.0bps"
    );
}

#[test]
fn forward_fifteen_minute_context_is_compact_and_non_authoritative() {
    let value = CohortForwardContext15mSummary {
        context_15m_observed: 3,
        context_15m_missing: 0,
        aligned: CohortForwardRegimeBucket {
            resolved: 2,
            total_net_return_bps: 44.0,
            ..CohortForwardRegimeBucket::default()
        },
        opposed: CohortForwardRegimeBucket::default(),
        neutral: CohortForwardRegimeBucket {
            resolved: 1,
            total_net_return_bps: -20.0,
            ..CohortForwardRegimeBucket::default()
        },
        unavailable: CohortForwardRegimeBucket::default(),
    };

    assert_eq!(
        context_15m_text(&value),
        "15M CONTEXT OBS 3/3 // ALIGNED N2 +44.0 // OPPOSED N0 +0.0 // NEUTRAL N1 -20.0bps // REPORT ONLY"
    );
}

#[test]
fn hype_hulk_squeeze_challenger_has_an_unambiguous_label() {
    let candidate = "hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1";

    assert_eq!(
        forward_title("HYPE", candidate, false),
        "FROZEN FWD HYPE HULK SQZ60"
    );
    assert_eq!(
        forward_detail_title("HYPE", candidate, false),
        "FROZEN HYPE HULK SQUEEZE-RELAXED FIXED 60M"
    );
}

#[test]
fn hype_range_absorption_challenger_has_an_unambiguous_label() {
    let candidate = "hype_range_absorption_fixed60_bidirectional_v1";

    assert_eq!(
        forward_title("HYPE", candidate, false),
        "FROZEN FWD HYPE ABSORB60"
    );
    assert_eq!(
        forward_detail_title("HYPE", candidate, false),
        "FROZEN HYPE OPPOSED-BOOK RANGE ABSORPTION 60M"
    );
}

#[test]
fn sol_aligned_range_challenger_has_an_unambiguous_label() {
    let candidate = "sol_aligned_range_relaxed_fixed60_bidirectional_v1";

    assert_eq!(
        forward_title("SOL", candidate, false),
        "FROZEN FWD SOL ALIGN60"
    );
    assert_eq!(
        forward_detail_title("SOL", candidate, false),
        "FROZEN SOL ALIGNED-BOOK RANGE RELAXATION 60M"
    );
}

#[test]
fn btc_hulk_money_flow_challenger_has_an_unambiguous_label() {
    let candidate = "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1";

    assert_eq!(
        forward_title("BTC", candidate, false),
        "FROZEN FWD BTC HULK FLOW60"
    );
    assert_eq!(
        forward_detail_title("BTC", candidate, false),
        "FROZEN BTC HULK MONEY-FLOW RELAXATION 60M"
    );
}

#[test]
fn aligned_book_breakout_relaxations_have_compact_unambiguous_labels() {
    let hype = "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1";
    let sol = "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1";

    assert_eq!(
        forward_title("HYPE", hype, false),
        "FROZEN FWD HYPE BK ALIGN60"
    );
    assert_eq!(
        forward_detail_title("HYPE", hype, false),
        "FROZEN HYPE ALIGNED-BOOK BREAKOUT RELAXATION 60M"
    );
    assert_eq!(
        forward_title("SOL", sol, false),
        "FROZEN FWD SOL BK ALIGN60"
    );
    assert_eq!(
        forward_detail_title("SOL", sol, false),
        "FROZEN SOL ALIGNED-BOOK BREAKOUT RELAXATION 60M"
    );
}

#[test]
fn generic_entry_context_survives_missing_hype_only_metrics() {
    let app = App::new("SOL".into(), "1m".into(), Vec::new(), false, false);
    let attempt = portfolio_attempt_without_hype_metrics();

    let rendered = pending_entry_context_line(&attempt, &app)
        .expect("generic entry context")
        .spans
        .iter()
        .map(|span| span.content.as_ref())
        .collect::<String>();

    assert_eq!(rendered, "ENTRY MTF 5M RANGE // STRUCT LONG");
}

#[test]
fn complete_entry_regime_tuple_is_visible_without_hype_metrics() {
    let app = App::new("SOL".into(), "1m".into(), Vec::new(), false, false);
    let mut attempt = portfolio_attempt_without_hype_metrics();
    attempt.primary_regime = Some("RANGE".into());
    attempt.state_1m = Some("TRANSITION".into());
    attempt.context_15m = Some("RANGE".into());

    let rendered = pending_entry_context_line(&attempt, &app)
        .expect("complete entry context")
        .spans
        .iter()
        .map(|span| span.content.as_ref())
        .collect::<String>();

    assert_eq!(
        rendered,
        "ENTRY MTF 1M TRANSITION // 5M RANGE // 15M RANGE // PRIMARY RANGE // STRUCT LONG"
    );
}

#[test]
fn portfolio_fit_leads_with_deployable_only_economics() {
    let journal = portfolio_journal();
    let app = App::new("BTC".into(), "1m".into(), Vec::new(), false, false);
    let line = portfolio_summary_line(&journal, &app);
    let rendered = line
        .spans
        .iter()
        .map(|span| span.content.as_ref())
        .collect::<String>();

    assert!(
        rendered.contains("INCR N4 2/2 NET -28.1bps PF 0.67 CONC 42%"),
        "{rendered}"
    );
}

#[test]
fn zero_deployable_outcomes_remain_explicit_without_concentration() {
    let mut journal = portfolio_journal();
    journal.attempts = 1;
    journal.deployable = 0;
    journal.deployable_resolved = Some(0);
    journal.deployable_wins = Some(0);
    journal.deployable_losses = Some(0);
    journal.deployable_total_net_return_bps = Some(0.0);
    journal.deployable_profit_factor = None;
    journal.deployable_largest_abs_contribution_fraction = None;
    journal.existing_symbol_position = 1;
    journal.resolved = 1;
    journal.pending = 0;

    assert_eq!(
        deployable_performance_text(&journal).as_deref(),
        Some("INCR N0 0/0 NET +0.0bps PF N/A")
    );
}

fn portfolio_journal() -> CohortCandidatePortfolioJournal {
    CohortCandidatePortfolioJournal {
        source_strategy_id: "source".into(),
        candidate_strategy_id: "candidate".into(),
        symbol: "HYPE".into(),
        attempts: 6,
        deployable: 4,
        deployable_resolved: Some(4),
        deployable_wins: Some(2),
        deployable_losses: Some(2),
        deployable_total_net_return_bps: Some(-28.135),
        deployable_profit_factor: Some(0.6676),
        deployable_largest_abs_contribution_fraction: Some(0.42),
        existing_symbol_position: 2,
        portfolio_capacity: 0,
        same_cycle_symbol_action: 0,
        portfolio_state_unavailable: 0,
        resolved: 5,
        pending: 1,
        latest_attempt: None,
    }
}

fn portfolio_attempt_without_hype_metrics() -> CohortCandidatePortfolioAttempt {
    CohortCandidatePortfolioAttempt {
        source_run_id: "bidirectional-live-a".into(),
        side: "long".into(),
        decision_time_ms: 1_785_923_280_000,
        classification: "deployable_flat_entry".into(),
        open_position_count: Some(2),
        available_position_slots: Some(2),
        outcome_status: "pending_or_unresolved".into(),
        net_return_bps: None,
        current_estimated_net_return_bps: Some(-9.0),
        mfe_bps: Some(0.3),
        mae_bps: Some(-24.6),
        remaining_ms: Some(300_000),
        current_exit_top_level_capacity: Some(true),
        primary_regime: None,
        state_1m: None,
        state_5m: Some("RANGE".into()),
        context_15m: None,
        structural_direction: Some("long".into()),
        breakout_volume_ratio: None,
        current_bbwp_percentile: None,
        regime_strength: None,
        same_cycle_action_count: 0,
        same_cycle_withheld_count: 0,
    }
}
