//! Compact operational status for the rolling read-only cohort analysis.

use ratatui::{
    Frame,
    layout::Rect,
    text::{Line, Span},
    widgets::Paragraph,
};

use crate::app::App;
use crate::backend_cohort_checkpoint::CohortCheckpointTelemetry;
use crate::backend_cohort_configuration::CohortConfigurationGeneration;
use crate::backend_cohort_maximum_hold::CohortMaximumHoldEvidence;
use crate::cohort_format::fill_time;
use crate::cohort_widgets::panel;

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let checkpoint = &app.backend.cohort_checkpoint;
    let stale_generation = stale_generation(checkpoint);
    let title = if stale_generation.is_some() {
        " ROLLING ANALYSIS // ARCHIVE EVIDENCE // STAGED UPDATE PENDING // READ-ONLY "
    } else {
        " ROLLING ANALYSIS // ARCHIVE EVIDENCE // READ-ONLY "
    };
    if !checkpoint.configured {
        render_issue(
            frame,
            app,
            area,
            title,
            "ANALYSIS NOT CONFIGURED // launcher must provide --cohort-checkpoint",
        );
        return;
    }
    if !checkpoint.available {
        let issue = checkpoint
            .issue
            .as_deref()
            .unwrap_or("checkpoint unavailable");
        render_issue(
            frame,
            app,
            area,
            title,
            &format!("ANALYSIS UNAVAILABLE // {issue}"),
        );
        return;
    }
    let line = if checkpoint.analysis_mode.as_deref() == Some("forward_observer") {
        observer_line(checkpoint)
    } else {
        live_line(checkpoint)
    };
    let mut lines = Vec::new();
    if let Some(generation) = stale_generation {
        lines.push(Line::from(Span::styled(
            configuration_warning(generation),
            app.theme.gate_blocked,
        )));
    }
    lines.push(Line::from(Span::styled(line, app.theme.cyan)));
    if checkpoint.analysis_mode.as_deref() == Some("live_execution") {
        lines.push(Line::from(Span::styled(
            maximum_hold_line(checkpoint.maximum_hold_decisions.as_ref()),
            app.theme.gold,
        )));
    }
    frame.render_widget(Paragraph::new(lines).block(panel(title, app)), area);
}

fn stale_generation(
    checkpoint: &CohortCheckpointTelemetry,
) -> Option<&CohortConfigurationGeneration> {
    checkpoint
        .configuration_generation
        .as_ref()
        .filter(|generation| !generation.matches_runtime)
}

fn configuration_warning(generation: &CohortConfigurationGeneration) -> String {
    format!(
        "RESTART WHEN FLAT | {} | RUN {} != CFG {}",
        restart_label(generation),
        fingerprint_prefix(&generation.runtime_profile_fingerprint),
        fingerprint_prefix(&generation.current_profile_fingerprint),
    )
}

fn restart_label(generation: &CohortConfigurationGeneration) -> String {
    match generation.restart_state.as_str() {
        "wait_for_flat_and_no_orders" => {
            format!("WAIT {} OPEN/ORDER", generation.blocking_assets.join(","))
        }
        "candidate_flat_no_orders" => "FLAT/ORDER-FREE CANDIDATE".into(),
        _ => "RESTART STATE UNAVAILABLE".into(),
    }
}

fn fingerprint_prefix(value: &str) -> String {
    value.chars().take(12).collect()
}

fn live_line(checkpoint: &CohortCheckpointTelemetry) -> String {
    let freshness = freshness(checkpoint);
    let lifecycle = human_token(checkpoint.lifecycle_state.as_deref().unwrap_or("unknown"));
    let coverage = match checkpoint.coverage_complete {
        Some(true) => "COVERAGE COMPLETE".into(),
        Some(false) => format!("GAPS {}", checkpoint.technical_gaps.len()),
        None => "COVERAGE UNKNOWN".into(),
    };
    let evaluations = optional_count("EVAL", checkpoint.readiness_evaluations);
    let run = run_performance(checkpoint);
    let all_time = all_time_performance(checkpoint);
    let evidence = human_token(checkpoint.evidence_state.as_deref().unwrap_or("unresolved"));
    format!(
        "{freshness} | {lifecycle} | {coverage} | {evaluations} | {run} | {all_time} | {evidence}"
    )
}

fn run_performance(checkpoint: &CohortCheckpointTelemetry) -> String {
    let count = checkpoint
        .closed_trades
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let pnl = checkpoint
        .net_pnl_usd
        .map_or_else(|| "N/A".into(), signed_amount);
    format!("RUN {count}C NET {pnl}")
}

fn all_time_performance(checkpoint: &CohortCheckpointTelemetry) -> String {
    let Some(history) = checkpoint.all_time_performance() else {
        return "ALL N/A".into();
    };
    format!(
        "ALL {}C NET {}",
        history.total.closed_trades,
        signed_amount(history.total.net_pnl_usd),
    )
}

fn observer_line(checkpoint: &CohortCheckpointTelemetry) -> String {
    let coverage = coverage(checkpoint);
    let evaluations = optional_count("FWD EVAL", checkpoint.forward_evaluations);
    let fires = optional_count("FIRE", checkpoint.eligible_signals);
    let paths = forward_paths(checkpoint);
    format!(
        "{} | FORWARD OBSERVER | {coverage} | {evaluations} | {fires} | {paths} | NO FILLS/PNL",
        freshness(checkpoint),
    )
}

fn forward_paths(checkpoint: &CohortCheckpointTelemetry) -> String {
    if checkpoint.forward_path_coverage_complete == Some(false) {
        return "5M PATH DATA GAP".into();
    }
    match (
        checkpoint.five_minute_paths_resolved,
        checkpoint.five_minute_paths_independent,
    ) {
        (Some(resolved), Some(independent)) => {
            format!("5M PATH {resolved}/{independent} INDEP")
        }
        _ => "5M PATH N/A".into(),
    }
}

fn freshness(checkpoint: &CohortCheckpointTelemetry) -> &'static str {
    if checkpoint.stale {
        "STALE >90S"
    } else {
        "FRESH"
    }
}

fn coverage(checkpoint: &CohortCheckpointTelemetry) -> String {
    match checkpoint.coverage_complete {
        Some(true) => "COVERAGE COMPLETE".into(),
        Some(false) => format!("GAPS {}", checkpoint.technical_gaps.len()),
        None => "COVERAGE UNKNOWN".into(),
    }
}

fn render_issue(frame: &mut Frame, app: &App, area: Rect, title: &str, message: &str) {
    frame.render_widget(
        Paragraph::new(message.to_string())
            .style(app.theme.gate_blocked)
            .block(panel(title, app)),
        area,
    );
}

fn optional_count(label: &str, value: Option<usize>) -> String {
    value.map_or_else(
        || format!("{label} N/A"),
        |count| format!("{label} {count}"),
    )
}

fn signed_amount(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

fn human_token(value: &str) -> String {
    value.replace('_', " ").to_uppercase()
}

fn maximum_hold_line(evidence: Option<&CohortMaximumHoldEvidence>) -> String {
    let Some(value) = evidence else {
        return "MAXH N/A // CHECKPOINT FIELD UNAVAILABLE".into();
    };
    let counts = format!(
        "MAXH {} K{}/X{}",
        value.observed, value.extended, value.exited
    );
    let extension = extension_outcome_line(value);
    let Some(latest) = value.latest_decisions.last() else {
        return extension.map_or_else(
            || format!("{counts} // NO SOFT-DEADLINE DECISION"),
            |extension| format!("{counts} // {extension}"),
        );
    };
    let side = if latest.side == "long" { "L" } else { "S" };
    let score = latest
        .structure_alignment_score
        .map_or_else(|| "N/A".into(), |score| format!("{score:+.2}"));
    let hard = latest
        .hard_deadline_timestamp_ms
        .map_or_else(|| "N/A".into(), fill_time);
    let decision = format!(
        "{counts} // LAST {} {side} {} A{score} // HARD {hard}",
        latest.symbol,
        latest.outcome.to_uppercase(),
    );
    extension.map_or(decision.clone(), |extension| {
        format!("{decision} | {extension}")
    })
}

fn extension_outcome_line(evidence: &CohortMaximumHoldEvidence) -> Option<String> {
    let extensions = evidence.extension_outcomes.as_ref()?;
    let latest = extensions.latest_outcomes.last()?;
    let provenance = if latest.causal_decision_recorded {
        "DECISION"
    } else {
        "PLAN-DERIVED"
    };
    let outcome = format!(
        "EXT {} LAST {} ACT-SOFT {} {provenance}",
        extensions.resolved,
        latest.symbol,
        signed_delta(latest.actual_minus_soft_net_usd),
    );
    let trail = extensions
        .post_soft_trail_challenger
        .as_ref()
        .and_then(|value| value.summary_by_giveback_bps.get(&30));
    Some(trail.map_or(outcome.clone(), |value| {
        format!(
            "{outcome} | TRAIL30 N{} HIT{} ΔACT {}",
            value.eligible,
            value.triggered,
            signed_delta(value.trail_minus_actual_net_usd),
        )
    }))
}

fn signed_delta(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend_cohort_maximum_hold::{
        CohortMaximumHoldDecision, CohortMaximumHoldEvidence,
    };
    use crate::backend_cohort_maximum_hold_extensions::{
        CohortMaximumHoldExtensionEvidence, CohortMaximumHoldExtensionOutcome,
    };
    use crate::backend_cohort_post_soft_trail::{
        CohortPostSoftTrailEvidence, CohortPostSoftTrailSummary,
    };
    use crate::backend_cohort_trade_performance::{
        CohortAllTimeTradePerformance, CohortTradePerformance, CohortTradePerformanceSummary,
    };
    use std::collections::BTreeMap;

    #[test]
    fn live_line_distinguishes_the_empty_run_from_populated_all_time_history() {
        let checkpoint = CohortCheckpointTelemetry {
            lifecycle_state: Some("running_consistent".into()),
            coverage_complete: Some(true),
            readiness_evaluations: Some(2_011),
            closed_trades: Some(0),
            net_pnl_usd: Some(0.0),
            evidence_state: Some("no_closed_trade_evidence".into()),
            trade_performance: Some(CohortTradePerformance {
                all_time_live: Some(CohortAllTimeTradePerformance {
                    total: CohortTradePerformanceSummary {
                        closed_trades: 15,
                        net_pnl_usd: 2.225858,
                        ..CohortTradePerformanceSummary::default()
                    },
                    ..CohortAllTimeTradePerformance::default()
                }),
                ..CohortTradePerformance::default()
            }),
            ..CohortCheckpointTelemetry::default()
        };

        let line = live_line(&checkpoint);

        assert!(line.contains("RUN 0C NET +$0.00"), "{line}");
        assert!(line.contains("ALL 15C NET +$2.23"), "{line}");
        assert!(!line.contains("| CLOSED 0 |"), "{line}");
    }

    #[test]
    fn live_line_preserves_an_explicit_zero_trade_accounting_epoch() {
        let checkpoint = CohortCheckpointTelemetry {
            closed_trades: Some(0),
            net_pnl_usd: Some(0.0),
            trade_performance: Some(CohortTradePerformance {
                all_time_live: Some(CohortAllTimeTradePerformance {
                    total: CohortTradePerformanceSummary::default(),
                    ..CohortAllTimeTradePerformance::default()
                }),
                ..CohortTradePerformance::default()
            }),
            ..CohortCheckpointTelemetry::default()
        };

        let line = live_line(&checkpoint);

        assert!(line.contains("RUN 0C NET +$0.00"), "{line}");
        assert!(line.contains("ALL 0C NET +$0.00"), "{line}");
    }

    #[test]
    fn maximum_hold_line_reports_exact_latest_boundary() {
        let evidence = CohortMaximumHoldEvidence {
            observed: 1,
            extended: 1,
            exited: 0,
            provider_symbols: 1,
            latest_decisions: vec![CohortMaximumHoldDecision {
                decision_id: "HYPE:99:soft_maximum_hold".into(),
                lifecycle_id: "HYPE:99".into(),
                symbol: "HYPE".into(),
                strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
                side: "long".into(),
                decision_time_ms: 1_785_812_712_230,
                opened_at_ms: 1_785_783_912_230,
                elapsed_ms: 28_800_000,
                soft_deadline_timestamp_ms: 1_785_812_712_230,
                hard_deadline_timestamp_ms: Some(1_785_870_312_230),
                outcome: "extend".into(),
                exit_reason: None,
                structure_alignment_score: Some(0.9167),
                structure_alignment_threshold: 0.5,
            }],
            extension_outcomes: None,
        };

        assert_eq!(
            maximum_hold_line(Some(&evidence)),
            "MAXH 1 K1/X0 // LAST HYPE L EXTEND A+0.92 // HARD 15:05:12 EDT"
        );
    }

    #[test]
    fn maximum_hold_line_surfaces_plan_derived_extension_result() {
        let evidence = CohortMaximumHoldEvidence {
            observed: 0,
            extended: 0,
            exited: 0,
            provider_symbols: 0,
            latest_decisions: vec![],
            extension_outcomes: Some(CohortMaximumHoldExtensionEvidence {
                resolved: 1,
                inferred_without_decision_event: 1,
                better_than_soft_reference: 0,
                worse_than_soft_reference: 1,
                unchanged_from_soft_reference: 0,
                actual_net_pnl_usd: 0.0966,
                estimated_soft_net_pnl_usd: 0.2482,
                actual_minus_soft_net_usd: -0.1516,
                latest_outcomes: vec![CohortMaximumHoldExtensionOutcome {
                    lifecycle_id: "HYPE:509351044526".into(),
                    symbol: "HYPE".into(),
                    strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
                    side: "long".into(),
                    extension_duration_ms: 3_322_862,
                    causal_decision_recorded: false,
                    actual_net_pnl_usd: 0.0966,
                    estimated_soft_net_pnl_usd: 0.2482,
                    actual_minus_soft_net_usd: -0.1516,
                }],
                post_soft_trail_challenger: Some(trail_evidence()),
            }),
        };

        assert_eq!(
            maximum_hold_line(Some(&evidence)),
            "MAXH 0 K0/X0 // EXT 1 LAST HYPE ACT-SOFT -$0.15 PLAN-DERIVED | TRAIL30 N1 HIT1 ΔACT +$0.06"
        );
    }

    fn trail_evidence() -> CohortPostSoftTrailEvidence {
        let summary = CohortPostSoftTrailSummary {
            eligible: 1,
            triggered: 1,
            not_triggered: 0,
            estimated_net_pnl_usd: 0.16,
            actual_net_pnl_usd: 0.0966,
            estimated_soft_net_pnl_usd: 0.2482,
            trail_minus_actual_net_usd: 0.0634,
            trail_minus_soft_net_usd: -0.0882,
        };
        CohortPostSoftTrailEvidence {
            summary_by_giveback_bps: BTreeMap::from([(30, summary)]),
            latest_results: vec![],
        }
    }
}
