use std::collections::BTreeMap;

use hypervector_tui::backend_cohort_profit_lock::{
    CohortHip3ProfitLockProspectiveEvidence, CohortProfitLockEvidence,
    CohortProfitLockNormalizedEvidence, CohortProfitLockNormalizedPartition,
    CohortProfitLockNormalizedSummary, CohortProfitLockPartition, CohortProfitLockSummary,
    CohortSupportDecayProfitLockEvidence,
};
use hypervector_tui::cohort_research_profit_lock::summary_texts;

#[test]
fn profit_lock_summary_separates_underperformance_from_small_sample_observation() {
    let texts = summary_texts(&evidence());

    assert!(texts[0].contains("ARCHIVE N8"));
    assert!(texts[0].contains("A40 -$1.10"));
    assert!(texts[1].contains("HYPE N5"));
    assert!(texts[1].contains("UNDERPERFORMED"));
    assert!(texts[1].contains("BTC HV N3"));
    assert!(texts[1].contains("OBSERVE"));
}

#[test]
fn support_decay_summary_is_explicitly_post_hoc_and_report_only() {
    let mut evidence = evidence();
    evidence.support_decay_all_time_live_mechanism = Some(support_decay());

    let texts = summary_texts(&evidence);

    assert_eq!(texts.len(), 3);
    assert!(texts[2].contains("REPORT ONLY"));
    assert!(texts[2].contains("POST-HOC"));
    assert!(texts[2].contains("SOL EXIT OBS"));
    assert!(texts[2].contains("DECAY<=0.25 X5 @60s NEXT-BAR"));
    assert!(texts[2].contains("A40 SOL N1/T1"));
    assert!(texts[2].contains("Δ+40.69bp"));
    assert!(texts[2].contains("ALL N18 Δ-30.17bp REJECT"));
    assert!(texts[2].contains("NO EXECUTION AUTHORITY"));
}

#[test]
fn hip3_prospective_summary_exposes_cutoff_and_zero_sample_truth() {
    let mut evidence = evidence();
    evidence.hip3_swing_60_30_prospective_mechanism =
        Some(CohortHip3ProfitLockProspectiveEvidence {
            entry_cutoff_timestamp_ms: 1_786_248_246_000,
            source_matching_lifecycles: 2,
            excluded_predeclaration_lifecycles: 2,
            prospective_lifecycles: 0,
            eligible_lifecycles: 0,
            triggered_lifecycles: 0,
            mean_delta_bps: None,
            evidence_state: "awaiting_post_cutoff_resolution".into(),
        });

    let texts = summary_texts(&evidence);

    assert_eq!(texts.len(), 3);
    assert!(texts[2].contains("HIP3 60/30 PROSPECTIVE"));
    assert!(texts[2].contains("POST-CUT N0/E0/T0"));
    assert!(texts[2].contains("PRE-CUT EXCLUDED 2"));
    assert!(texts[2].contains("ΔN/A"));
    assert!(texts[2].contains("NO EXECUTION AUTHORITY"));
}

fn evidence() -> CohortProfitLockEvidence {
    CohortProfitLockEvidence {
        summary_by_policy: summaries(-1.29, -1.10, -1.12, 8),
        by_provider_symbol: BTreeMap::from([
            (
                "hype_breakout_onset_bidirectional_v1|HYPE".into(),
                partition(-1.23, -1.21, -1.15, 5),
            ),
            (
                "hypervelocity_source_follow_bidirectional_5m_v1|BTC".into(),
                partition(0.05, 0.10, 0.02, 3),
            ),
        ]),
        current_run: partition(-0.16, -0.19, -0.16, 2),
        all_time_live_mechanism: None,
        support_decay_all_time_live_mechanism: None,
        hip3_swing_60_30_prospective_mechanism: None,
    }
}

fn support_decay() -> CohortSupportDecayProfitLockEvidence {
    let sol = CohortProfitLockNormalizedPartition {
        closed_lifecycles: 1,
        summary_by_policy: BTreeMap::from([
            ("a25_floor15_trail10".into(), normalized(-18.72, 1)),
            ("a40_floor15_trail20".into(), normalized(40.6864, 1)),
            ("a60_floor15_trail30".into(), normalized(0.0, 0)),
        ]),
    };
    CohortSupportDecayProfitLockEvidence {
        support_decay_threshold: 0.25,
        persistence_decisions: 5,
        decision_interval_ms: 60_000,
        same_bar_activation_and_trigger_allowed: false,
        mechanism: CohortProfitLockNormalizedEvidence {
            source_profile_count: 5,
            source_run_count: 8,
            summary_by_policy: BTreeMap::from([
                ("a25_floor15_trail10".into(), normalized_all(-31.74)),
                ("a40_floor15_trail20".into(), normalized_all(-30.1653)),
                ("a60_floor15_trail30".into(), normalized_all(-28.41)),
            ]),
            by_provider_symbol: BTreeMap::from([(
                "hype_breakout_onset_bidirectional_v1|SOL".into(),
                sol,
            )]),
        },
    }
}

fn normalized_all(delta: f64) -> CohortProfitLockNormalizedSummary {
    CohortProfitLockNormalizedSummary {
        eligible: 18,
        triggered: 9,
        mean_estimated_bps: Some(42.45 + delta),
        mean_actual_bps: Some(42.45),
        mean_delta_bps: Some(delta),
        profit_factor: Some(1.65),
    }
}

fn normalized(delta: f64, triggered: usize) -> CohortProfitLockNormalizedSummary {
    CohortProfitLockNormalizedSummary {
        eligible: 1,
        triggered,
        mean_estimated_bps: Some(10.0 + delta),
        mean_actual_bps: Some(10.0),
        mean_delta_bps: Some(delta),
        profit_factor: None,
    }
}

fn partition(a25: f64, a40: f64, a60: f64, closed: usize) -> CohortProfitLockPartition {
    CohortProfitLockPartition {
        closed_lifecycles: closed,
        summary_by_policy: summaries(a25, a40, a60, closed),
    }
}

fn summaries(
    a25: f64,
    a40: f64,
    a60: f64,
    closed: usize,
) -> BTreeMap<String, CohortProfitLockSummary> {
    BTreeMap::from([
        ("a25_floor15_trail10".into(), summary(a25, closed)),
        ("a40_floor15_trail20".into(), summary(a40, closed)),
        ("a60_floor15_trail30".into(), summary(a60, closed)),
    ])
}

fn summary(delta: f64, closed: usize) -> CohortProfitLockSummary {
    CohortProfitLockSummary {
        eligible: closed,
        triggered: closed.saturating_sub(1),
        estimated_net_usd: 1.0 + delta,
        actual_net_usd: 1.0,
        delta_net_usd: delta,
        profit_factor: Some(1.5),
    }
}
