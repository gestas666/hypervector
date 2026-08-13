//! Compact truthful display of the report-only HYPE L2 Ridge observer.

use ratatui::{
    Frame,
    layout::Rect,
    text::{Line, Span},
    widgets::Paragraph,
};

use crate::app::App;
use crate::backend_hype_l2_observer::{
    HypeL2ObservationTelemetry, HypeL2ObserverTelemetry, HypeL2OutcomeSummaryTelemetry,
    HypeL2OutcomeTelemetry,
};
use crate::cohort_widgets::panel;

/// Format the observer as two compact rows without manufacturing zero values.
pub fn summary_text(status: &HypeL2ObserverTelemetry, now_ms: i64) -> Vec<String> {
    if !status.configured {
        return vec![
            "HYPE L2 RIDGE // NOT CONFIGURED".into(),
            "ANNOTATION UNAVAILABLE // NO EXECUTION AUTHORITY".into(),
        ];
    }
    if !status.available {
        return vec![
            "HYPE L2 RIDGE // STATUS UNAVAILABLE".into(),
            format!(
                "{} // NO EXECUTION AUTHORITY",
                status.issue.as_deref().unwrap_or("NO VALID STATUS")
            ),
        ];
    }
    vec![
        health_text(status, now_ms),
        observation_text(status),
        outcome_text(status),
    ]
}

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let rows = summary_text(
        &app.backend.hype_l2_observer,
        chrono::Utc::now().timestamp_millis(),
    );
    let lines = rows
        .into_iter()
        .enumerate()
        .map(|(index, row)| {
            let style = if index == 1 {
                app.theme.gold
            } else {
                app.theme.cyan
            };
            Line::from(Span::styled(row, style))
        })
        .collect::<Vec<_>>();
    frame.render_widget(
        Paragraph::new(lines).block(panel(" HYPE L2 RIDGE // PROSPECTIVE MODEL ", app)),
        area,
    );
}

fn health_text(status: &HypeL2ObserverTelemetry, now_ms: i64) -> String {
    let lifecycle = status.state.as_deref().unwrap_or("UNKNOWN").to_uppercase();
    let freshness = if status.stale { "STALE" } else { "FRESH" };
    let books = status
        .durable_books_observed
        .map_or_else(|| "N/A BOOKS".into(), |value| format!("{value} BOOKS"));
    let age = status
        .last_book_exchange_ts_ms
        .map_or_else(|| "BOOK N/A".into(), |value| book_age(value, now_ms));
    format!("HYPE L2 RIDGE // {lifecycle} {freshness} // {books} // {age} // AUTH NONE")
}

fn book_age(last_book_ms: i64, now_ms: i64) -> String {
    let seconds = now_ms.saturating_sub(last_book_ms).max(0) as f64 / 1_000.0;
    format!("BOOK {seconds:.1}s")
}

fn observation_text(status: &HypeL2ObserverTelemetry) -> String {
    if status.stale {
        return format!(
            "{} // ANNOTATION UNAVAILABLE // NO EXECUTION AUTHORITY",
            status
                .issue
                .as_deref()
                .unwrap_or("OBSERVER STATUS IS STALE")
        );
    }
    let Some(observation) = status.latest_observation.as_ref() else {
        return "WARM / WAITING FUTURE HYPE ENTRY // ANNOTATION ONLY // NO EXECUTION AUTHORITY"
            .into();
    };
    if observation.status == "coverage_unavailable" {
        return unavailable_observation(observation);
    }
    scored_observation(observation)
}

fn unavailable_observation(observation: &HypeL2ObservationTelemetry) -> String {
    format!(
        "LATEST {} COVERAGE UNAVAILABLE // {} // ANNOTATION ONLY",
        observation.side.as_deref().unwrap_or("N/A").to_uppercase(),
        observation
            .reason
            .as_deref()
            .unwrap_or("NO REASON REPORTED")
    )
}

fn scored_observation(observation: &HypeL2ObservationTelemetry) -> String {
    let side = observation.side.as_deref().unwrap_or("N/A").to_uppercase();
    let score = observation
        .predicted_gross_return_bps
        .map_or_else(|| "N/A".into(), |value| format!("{value:+.2}bps"));
    let percentile = observation
        .training_score_percentile
        .map_or_else(|| "N/A".into(), |value| format!("P{:.0}", value * 100.0));
    let coverage = coverage_text(observation);
    format!("LATEST {side} {score} // TRAIN {percentile} // {coverage} // ANNOTATION ONLY")
}

fn coverage_text(observation: &HypeL2ObservationTelemetry) -> String {
    let books = observation
        .coverage
        .books
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let gap = observation
        .coverage
        .maximum_interval_ms
        .map_or_else(|| "N/A".into(), |value| format!("{value}ms"));
    format!("COV {books} / GAP {gap}")
}

fn outcome_text(status: &HypeL2ObserverTelemetry) -> String {
    let Some(summary) = status.outcome_summary.as_ref() else {
        return "OUTCOME JOIN N/A // WAITING CHECKPOINT PROJECTION".into();
    };
    if summary.status == "unavailable" {
        return format!(
            "OUTCOME JOIN UNAVAILABLE // {}",
            summary
                .technical_issue
                .as_deref()
                .unwrap_or("NO TECHNICAL ISSUE REPORTED")
        );
    }
    observed_outcome_text(summary)
}

fn observed_outcome_text(summary: &HypeL2OutcomeSummaryTelemetry) -> String {
    let resolved = summary.counts.as_ref().map_or(0, |counts| counts.resolved);
    let Some(outcome) = summary.latest_outcome.as_ref() else {
        return format!("OUTCOMES {resolved} RESOLVED // WAITING SCORED ENTRY");
    };
    match outcome.status.as_str() {
        "open" => open_outcome_text(outcome, resolved),
        "resolved" => resolved_outcome_text(outcome, summary),
        state => format!(
            "VENUE {} // MODEL {} // RESOLVED {resolved}",
            state.replace('_', " ").to_uppercase(),
            bps(outcome.predicted_gross_return_bps)
        ),
    }
}

fn open_outcome_text(outcome: &HypeL2OutcomeTelemetry, resolved: usize) -> String {
    format!(
        "VENUE OPEN // MARK NET {} ({}) // MODEL {} // RESOLVED {resolved}",
        bps(outcome.marked_net_return_bps),
        usd(outcome.marked_net_pnl_usd),
        bps(outcome.predicted_gross_return_bps),
    )
}

fn resolved_outcome_text(
    outcome: &HypeL2OutcomeTelemetry,
    summary: &HypeL2OutcomeSummaryTelemetry,
) -> String {
    let performance = summary.resolved_performance.as_ref();
    let record = performance.map_or_else(
        || "N/A".into(),
        |value| format!("{}W/{}L", value.wins, value.losses),
    );
    let factor = performance.and_then(|value| value.profit_factor);
    format!(
        "VENUE RESOLVED NET {} ({}) // MODEL {} // CAL {record} PF {}",
        bps(outcome.actual_net_return_bps),
        usd(outcome.net_pnl_usd),
        bps(outcome.predicted_gross_return_bps),
        factor.map_or_else(|| "N/A".into(), |value| format!("{value:.2}")),
    )
}

fn bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.2}bps"))
}

fn usd(value: Option<f64>) -> String {
    value.map_or_else(|| "$N/A".into(), |number| format!("{number:+.2}$"))
}
