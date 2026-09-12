//! Recorded strategy clocks and causal canonical context for planning.

use chrono::DateTime;

use crate::backend_cohort::{CohortProvider, CohortProviderEvaluation};
use crate::cohort_format::fill_full_date_time;
use crate::cohort_open_hold::duration_label;

const CANONICAL_PROVIDER: &str = "canonical_regime_telemetry_v1";

/// Select the published signal clock without borrowing another route's metrics.
pub(crate) fn signal_timeframe<'a>(
    provider: &'a CohortProvider,
    evaluation: Option<&'a CohortProviderEvaluation>,
) -> &'a str {
    let metric = evaluation
        .filter(|value| {
            value.strategy_id == provider.strategy_id && provider.symbols.contains(&value.symbol)
        })
        .and_then(|value| value.readiness.metrics.get("signal_timeframe"));
    match metric {
        Some(value) => value
            .as_str()
            .filter(|text| !text.is_empty())
            .unwrap_or("N/A"),
        None => &provider.timeframe,
    }
}

/// Show time since the actual observation, separately from arrival latency.
pub(crate) fn evidence_age(value: &CohortProviderEvaluation, now: Option<u64>) -> String {
    let age = observed_ms(value).and_then(|at| now?.checked_sub(at));
    age.map_or_else(
        || "DATA AGE INVALID/UNKNOWN".into(),
        |age| format!("DATA AGE {}", duration_label(age)),
    )
}

/// Keep prior causal context and latest recorded context visibly distinct.
pub(crate) fn planning_lines(
    value: &CohortProviderEvaluation,
    history: &[CohortProviderEvaluation],
    now: Option<u64>,
) -> Vec<String> {
    let prior = canonical_at_decision(value, history);
    let latest = history
        .iter()
        .filter(|row| canonical_for(row, &value.symbol))
        .max_by_key(|row| row.decision_time_ms);
    let mut lines = vec![
        "BACKEND EVIDENCE ONLY // STRATEGY / CANONICAL CONTEXT".into(),
        evidence_age(value, now),
    ];
    lines.extend(context_lines("AT DECISION", prior, now));
    if let Some(prior) = prior {
        lines.push(format!(
            "CANONICAL BAR PRECEDES DECISION BY {}",
            duration_label(value.decision_time_ms - prior.decision_time_ms),
        ));
    }
    lines.extend(context_lines("LATEST RECORDED", latest, now));
    lines.push("CONTEXT ONLY // PROVIDER ENTRY RULES REMAIN SEPARATE".into());
    lines
}

fn canonical_at_decision<'a>(
    value: &CohortProviderEvaluation,
    history: &'a [CohortProviderEvaluation],
) -> Option<&'a CohortProviderEvaluation> {
    let observed = observed_ms(value)?;
    history
        .iter()
        .filter(|row| {
            canonical_for(row, &value.symbol)
                && row.decision_time_ms <= value.decision_time_ms
                && observed_ms(row).is_some_and(|at| at <= observed)
        })
        .max_by_key(|row| row.decision_time_ms)
}

fn canonical_for(value: &CohortProviderEvaluation, symbol: &str) -> bool {
    value.strategy_id == CANONICAL_PROVIDER && value.symbol == symbol
}

fn observed_ms(value: &CohortProviderEvaluation) -> Option<u64> {
    DateTime::parse_from_rfc3339(&value.observed_at)
        .ok()
        .and_then(|at| u64::try_from(at.timestamp_millis()).ok())
        .filter(|at| value.decision_time_ms > 0 && *at >= value.decision_time_ms)
}

fn context_lines(
    label: &str,
    value: Option<&CohortProviderEvaluation>,
    now: Option<u64>,
) -> Vec<String> {
    let Some(value) = value else {
        return vec![format!(
            "{label}: CANONICAL UNAVAILABLE IN RETAINED HISTORY"
        )];
    };
    vec![
        format!(
            "{label}: {} // {}",
            fill_full_date_time(value.decision_time_ms),
            evidence_age(value, now)
        ),
        format!(
            "CANONICAL 1M {} // 5M {} // 15M {}",
            value.state_1m.as_deref().unwrap_or("N/A"),
            value.state_5m.as_deref().unwrap_or("N/A"),
            value.context_15m.as_deref().unwrap_or("N/A"),
        ),
    ]
}

#[cfg(test)]
#[path = "cohort_strategy_context_tests.rs"]
mod tests;
