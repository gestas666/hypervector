//! Honest TUI summary for the exact ETH eligible-policy observer.

use ratatui::text::{Line, Span};

use crate::{
    app::App,
    backend_cohort_eligible_policy_forward::{
        CohortEligiblePolicyAttempt, CohortEligiblePolicyForward,
    },
};

const MILLIS_PER_MINUTE: u64 = 60_000;

/// Return compact plain-text evidence suitable for tests and narrow terminals.
pub fn summary_texts(evidence: &CohortEligiblePolicyForward) -> Vec<String> {
    let funding_scope = if evidence.funding_included {
        "OFFICIAL FUNDING"
    } else {
        "BEFORE FUNDING"
    };
    let mut lines = vec![
        format!(
            "{} V12 EXACT POLICY // REPORT ONLY // 60 BPS STOP / 12H HOLD / 13 BPS FRICTION // {}",
            evidence.symbol, funding_scope
        ),
        format!(
            "SIGNALS {} // SELECTED {} // PENDING {} // RESOLVED {} // MISSING {} // PORTFOLIO FIT {}/{}",
            evidence.eligible_signals,
            evidence.selected_non_overlapping,
            evidence.pending,
            evidence.resolved,
            evidence.missing_data,
            evidence.deployable,
            evidence.portfolio_attempts,
        ),
    ];
    if let Some(attempt) = &evidence.latest_attempt {
        lines.extend(attempt_texts(attempt));
    }
    lines
}

pub(crate) fn line_count(evidence: &CohortEligiblePolicyForward) -> u16 {
    u16::try_from(summary_texts(evidence).len()).unwrap_or(u16::MAX)
}

pub(crate) fn lines(evidence: &CohortEligiblePolicyForward, app: &App) -> Vec<Line<'static>> {
    summary_texts(evidence)
        .into_iter()
        .enumerate()
        .map(|(index, text)| {
            let style = match index {
                0 => app.theme.cyan,
                1 => app.theme.title,
                2 => app.theme.gold,
                _ => app.theme.muted,
            };
            Line::from(Span::styled(text, style))
        })
        .collect()
}

fn attempt_texts(attempt: &CohortEligiblePolicyAttempt) -> [String; 2] {
    let bars = attempt
        .observed_candles
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let status = attempt.status.replace('_', " ").to_uppercase();
    let mark = funded_mark_text(attempt);
    [
        format!(
            "LATEST {} {} @ ${:.2} // {} BARS // {}",
            attempt.side.to_uppercase(),
            status,
            attempt.reference_price,
            bars,
            mark,
        ),
        format!(
            "PATH MFE {} BPS // MAE {} BPS // {} LEFT // FILL NOT PROVEN",
            bps(attempt.mfe_bps),
            bps(attempt.mae_bps),
            remaining(attempt.remaining_ms),
        ),
    ]
}

fn funded_mark_text(attempt: &CohortEligiblePolicyAttempt) -> String {
    match (
        attempt.funding_bps,
        attempt.current_estimated_net_after_funding_bps,
    ) {
        (Some(funding), Some(after)) => format!(
            "MARK {} BPS GROSS / BEFORE {} / FUND {funding:+.1} / NET {after:+.1} BPS",
            bps(attempt.current_gross_return_bps),
            bps(attempt.current_estimated_net_before_funding_bps),
        ),
        _ => format!(
            "MARK {} BPS GROSS / {} BPS BEFORE FUNDING",
            bps(attempt.current_gross_return_bps),
            bps(attempt.current_estimated_net_before_funding_bps),
        ),
    }
}

fn bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.1}"))
}

fn remaining(value: Option<u64>) -> String {
    value.map_or_else(
        || "N/A".into(),
        |millis| format!("{}M", millis / MILLIS_PER_MINUTE),
    )
}
