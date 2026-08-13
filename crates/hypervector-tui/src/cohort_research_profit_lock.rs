//! Compact research-cockpit rendering of report-only profit-lock evidence.

use std::collections::BTreeMap;

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_profit_lock::{
    CohortHip3ProfitLockProspectiveEvidence, CohortProfitLockEvidence,
    CohortProfitLockNormalizedEvidence, CohortProfitLockNormalizedPartition,
    CohortProfitLockNormalizedSummary, CohortProfitLockPartition, CohortProfitLockSummary,
};

const A25: &str = "a25_floor15_trail10";
const A40: &str = "a40_floor15_trail20";
const A60: &str = "a60_floor15_trail30";
const HYPE: &str = "hype_breakout_onset_bidirectional_v1|HYPE";
const BTC_HV: &str = "hypervelocity_source_follow_bidirectional_5m_v1|BTC";
const SOL: &str = "hype_breakout_onset_bidirectional_v1|SOL";

/// Render two high-signal lines without implying execution authority.
pub(crate) fn lines(evidence: &CohortProfitLockEvidence, app: &App) -> Vec<Line<'static>> {
    let text = summary_texts(evidence);
    let archive_style = if evidence
        .summary_by_policy
        .values()
        .all(|value| value.delta_net_usd < 0.0)
    {
        app.theme.bear
    } else {
        app.theme.gold
    };
    text.into_iter()
        .enumerate()
        .map(|(index, value)| {
            let style = if index == 0 {
                archive_style
            } else {
                app.theme.gold
            };
            Line::from(Span::styled(value, style))
        })
        .collect()
}

/// Build deterministic labels for snapshot tests and terminal rendering.
pub fn summary_texts(evidence: &CohortProfitLockEvidence) -> Vec<String> {
    let mut text = if let Some(all_time) = &evidence.all_time_live_mechanism {
        normalized_summary_texts(all_time, evidence).to_vec()
    } else {
        compatible_summary_texts(evidence).to_vec()
    };
    if let Some(support_decay) = &evidence.support_decay_all_time_live_mechanism {
        text.push(support_decay_text(support_decay));
    }
    if let Some(prospective) = &evidence.hip3_swing_60_30_prospective_mechanism {
        text.push(hip3_prospective_text(prospective));
    }
    text
}

/// Number of research summary rows required by the projected evidence.
pub(crate) fn line_count(evidence: Option<&CohortProfitLockEvidence>) -> u16 {
    evidence.map_or(0, |value| {
        u16::try_from(summary_texts(value).len()).unwrap_or(u16::MAX)
    })
}

fn support_decay_text(
    evidence: &crate::backend_cohort_profit_lock::CohortSupportDecayProfitLockEvidence,
) -> String {
    let sol = evidence.mechanism.by_provider_symbol.get(SOL);
    let a40 = sol.and_then(|partition| partition.summary_by_policy.get(A40));
    let all_a40 = evidence.mechanism.summary_by_policy.get(A40);
    let all_n = normalized_count(&evidence.mechanism.summary_by_policy);
    format!(
        "REPORT ONLY // POST-HOC SOL EXIT OBS // DECAY<={:.2} X{} @{}s NEXT-BAR // A40 SOL N{}/T{} EST {} ACT {} {} // ALL N{} {} REJECT // NO EXECUTION AUTHORITY",
        evidence.support_decay_threshold,
        evidence.persistence_decisions,
        evidence.decision_interval_ms / 1_000,
        sol.map_or(0, |partition| partition.closed_lifecycles),
        a40.map_or(0, |summary| summary.triggered),
        normalized_value(a40.and_then(|summary| summary.mean_estimated_bps)),
        normalized_value(a40.and_then(|summary| summary.mean_actual_bps)),
        normalized_delta(a40),
        all_n,
        normalized_delta(all_a40),
    )
}

fn hip3_prospective_text(evidence: &CohortHip3ProfitLockProspectiveEvidence) -> String {
    let state = evidence.evidence_state.replace('_', " ").to_uppercase();
    format!(
        "HIP3 60/30 PROSPECTIVE // CUT 2026-08-09 04:04Z // POST-CUT N{}/E{}/T{} // {} // PRE-CUT EXCLUDED {} // {} // NO EXECUTION AUTHORITY",
        evidence.prospective_lifecycles,
        evidence.eligible_lifecycles,
        evidence.triggered_lifecycles,
        normalized_delta_value(evidence.mean_delta_bps),
        evidence.excluded_predeclaration_lifecycles,
        state,
    )
}

fn normalized_delta_value(value: Option<f64>) -> String {
    value.map_or_else(
        || "ΔN/A".into(),
        |delta| format!("Δ{}{delta:.2}bp", if delta < 0.0 { "" } else { "+" }),
    )
}

fn normalized_value(value: Option<f64>) -> String {
    value.map_or_else(
        || "N/A".into(),
        |value| format!("{}{value:.2}bp", if value < 0.0 { "" } else { "+" }),
    )
}

fn normalized_summary_texts(
    all_time: &CohortProfitLockNormalizedEvidence,
    compatible: &CohortProfitLockEvidence,
) -> [String; 2] {
    let archive_n = normalized_count(&all_time.summary_by_policy);
    let archive = format!(
        "LOCK LAB // REPORT ONLY // ALL-LIVE N{archive_n} MIXED CONTRACTS // A25 {} | A40 {} | A60 {}",
        normalized_delta(all_time.summary_by_policy.get(A25)),
        normalized_delta(all_time.summary_by_policy.get(A40)),
        normalized_delta(all_time.summary_by_policy.get(A60)),
    );
    let providers = [
        normalized_provider("HYPE", all_time.by_provider_symbol.get(HYPE)),
        normalized_provider("BTC HV", all_time.by_provider_symbol.get(BTC_HV)),
        Some(format!(
            "CURRENT RUN N{}",
            compatible.current_run.closed_lifecycles
        )),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>()
    .join(" // ");
    [archive, providers]
}

fn compatible_summary_texts(evidence: &CohortProfitLockEvidence) -> [String; 2] {
    let archive_n = evidence
        .summary_by_policy
        .values()
        .map(|value| value.eligible)
        .max()
        .unwrap_or(0);
    let archive = format!(
        "EARLY LOCK // REPORT ONLY // ARCHIVE N{archive_n} // A25 {} | A40 {} | A60 {}",
        delta(evidence.summary_by_policy.get(A25)),
        delta(evidence.summary_by_policy.get(A40)),
        delta(evidence.summary_by_policy.get(A60)),
    );
    let providers = [
        provider_summary("HYPE", evidence.by_provider_symbol.get(HYPE)),
        provider_summary("BTC HV", evidence.by_provider_symbol.get(BTC_HV)),
        provider_summary("RUN", Some(&evidence.current_run)),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>()
    .join(" // ");
    [archive, providers]
}

fn normalized_provider(
    label: &str,
    partition: Option<&CohortProfitLockNormalizedPartition>,
) -> Option<String> {
    let partition = partition?;
    let (policy, result) = normalized_best_policy(partition)?;
    let assessment = if result.mean_delta_bps.is_some_and(|value| value < 0.0) {
        "UNDERPERFORMED"
    } else {
        "OBSERVE"
    };
    Some(format!(
        "{label} N{} BEST {} {} {assessment}",
        partition.closed_lifecycles,
        short_policy(policy),
        normalized_delta(Some(result)),
    ))
}

fn normalized_best_policy(
    partition: &CohortProfitLockNormalizedPartition,
) -> Option<(&str, &CohortProfitLockNormalizedSummary)> {
    partition
        .summary_by_policy
        .iter()
        .filter_map(|(policy, result)| result.mean_delta_bps.map(|value| (policy, result, value)))
        .max_by(|left, right| left.2.total_cmp(&right.2))
        .map(|(policy, result, _)| (policy.as_str(), result))
}

fn normalized_count(values: &BTreeMap<String, CohortProfitLockNormalizedSummary>) -> usize {
    values
        .values()
        .map(|value| value.eligible)
        .max()
        .unwrap_or(0)
}

fn normalized_delta(value: Option<&CohortProfitLockNormalizedSummary>) -> String {
    value.and_then(|result| result.mean_delta_bps).map_or_else(
        || "ΔN/A".into(),
        |delta| format!("Δ{}{:.2}bp", if delta < 0.0 { "" } else { "+" }, delta),
    )
}

fn provider_summary(label: &str, partition: Option<&CohortProfitLockPartition>) -> Option<String> {
    let partition = partition?;
    let (policy, result) = best_policy(partition)?;
    let assessment = if result.delta_net_usd < 0.0 {
        "UNDERPERFORMED"
    } else {
        "OBSERVE"
    };
    Some(format!(
        "{label} N{} BEST {} {} {assessment}",
        partition.closed_lifecycles,
        short_policy(policy),
        signed_money(result.delta_net_usd),
    ))
}

fn best_policy(partition: &CohortProfitLockPartition) -> Option<(&str, &CohortProfitLockSummary)> {
    partition
        .summary_by_policy
        .iter()
        .max_by(|left, right| left.1.delta_net_usd.total_cmp(&right.1.delta_net_usd))
        .map(|(policy, result)| (policy.as_str(), result))
}

fn delta(value: Option<&CohortProfitLockSummary>) -> String {
    value.map_or_else(|| "N/A".into(), |result| signed_money(result.delta_net_usd))
}

fn signed_money(value: f64) -> String {
    if value < 0.0 {
        format!("-${:.2}", value.abs())
    } else {
        format!("+${value:.2}")
    }
}

fn short_policy(value: &str) -> &'static str {
    match value {
        A25 => "A25",
        A40 => "A40",
        A60 => "A60",
        _ => "UNKNOWN",
    }
}
