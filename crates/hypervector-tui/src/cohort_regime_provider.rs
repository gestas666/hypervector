//! Provider trend context for assets without canonical regime classification.

use ratatui::{
    Frame,
    layout::Rect,
    text::{Line, Span},
    widgets::{Paragraph, Wrap},
};
use serde_json::Value;

use crate::app::App;
use crate::backend_cohort::CohortProviderEvaluation;
use crate::cohort_format::fill_time;
use crate::cohort_widgets::{panel, provider_alias, render_empty};

/// Render the selected asset's provider evidence without promoting it to a regime label.
pub(crate) fn render_focus(frame: &mut Frame, app: &App, area: Rect, symbol: &str) {
    let values = provider_evaluations(app, symbol);
    if values.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " CANONICAL REGIME NOT CLASSIFIED ",
            "NO PROVIDER EVALUATION REPORTED",
        );
        return;
    }
    let block = panel(
        format!(" COMPRESSION + BREAKOUT ENGINE // {symbol} // PROVIDER CONTEXT "),
        app,
    );
    let inner = block.inner(area);
    frame.render_widget(block, area);
    frame.render_widget(
        Paragraph::new(focus_lines(app, &values)).wrap(Wrap { trim: true }),
        inner,
    );
}

/// Render a compact provider signal stack for assets outside canonical regime coverage.
pub(crate) fn render_compact(frame: &mut Frame, app: &App, area: Rect, symbol: &str) {
    let values = provider_evaluations(app, symbol);
    if values.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " TREND STACK // PROVIDER CONTEXT ",
            "NO PROVIDER EVALUATION REPORTED",
        );
        return;
    }
    let lines = values
        .iter()
        .take(3)
        .map(|value| compact_line(app, value))
        .collect::<Vec<_>>();
    frame.render_widget(
        Paragraph::new(lines).block(panel(
            format!(" TREND STACK // {symbol} // PROVIDER CONTEXT "),
            app,
        )),
        area,
    );
}

fn focus_lines<'a>(app: &'a App, values: &[&'a CohortProviderEvaluation]) -> Vec<Line<'a>> {
    let mut lines = vec![
        Line::from("CANONICAL REGIME NOT CLASSIFIED // 1M/5M/15M"),
        Line::from(Span::styled(
            "PROVIDER TELEMETRY // REPORT ONLY // NO REGIME SUBSTITUTION",
            app.theme.muted,
        )),
    ];
    for value in values.iter().take(3) {
        lines.extend(provider_lines(app, value));
    }
    lines
}

fn provider_lines<'a>(app: &'a App, value: &'a CohortProviderEvaluation) -> Vec<Line<'a>> {
    let timeframe = metric_text(value, "source_timeframe").unwrap_or("N/A");
    let indicators = if value.readiness.indicators.is_empty() {
        "INDICATORS NOT REPORTED".into()
    } else {
        value.readiness.indicators.join("  //  ")
    };
    vec![
        Line::from(vec![
            Span::styled(provider_alias(&value.strategy_id), app.theme.title),
            Span::raw(format!(
                "  //  TF {timeframe}  //  {}",
                fill_time(value.decision_time_ms)
            )),
        ]),
        Line::from(format!(
            "PROVIDER SIGNAL {}  //  ENTRY ELIGIBLE {}  //  READY {:.0}%",
            crate::cohort_provider_action::action_label(value),
            if value.eligible { "YES" } else { "NO" },
            value.readiness.readiness_fraction * 100.0,
        )),
        reason_line(app, value),
        Line::from(indicators),
    ]
}

fn reason_line<'a>(app: &'a App, value: &'a CohortProviderEvaluation) -> Line<'a> {
    let reason = value.reason.replace('_', " ").to_uppercase();
    let blocker = value
        .readiness
        .blockers
        .first()
        .map(|item| item.replace('_', " ").to_uppercase());
    let suffix = blocker.map_or_else(String::new, |item| format!("  //  BLOCK {item}"));
    Line::from(Span::styled(
        format!("WHY {reason}{suffix}"),
        app.theme.gold,
    ))
}

fn compact_line<'a>(app: &'a App, value: &'a CohortProviderEvaluation) -> Line<'a> {
    Line::from(vec![
        Span::styled(provider_alias(&value.strategy_id), app.theme.title),
        Span::raw(format!(
            "  {:>4}  {:>3}  {:>3.0}%",
            crate::cohort_provider_action::action_label(value),
            if value.eligible { "YES" } else { "NO" },
            value.readiness.readiness_fraction * 100.0,
        )),
    ])
}

fn provider_evaluations<'a>(app: &'a App, symbol: &str) -> Vec<&'a CohortProviderEvaluation> {
    let mut values = app
        .backend
        .cohort
        .evaluations
        .iter()
        .filter(|value| value.symbol == symbol)
        .collect::<Vec<_>>();
    values.sort_by(|left, right| {
        right
            .decision_time_ms
            .cmp(&left.decision_time_ms)
            .then_with(|| left.strategy_id.cmp(&right.strategy_id))
    });
    values
}

fn metric_text<'a>(value: &'a CohortProviderEvaluation, key: &str) -> Option<&'a str> {
    value.readiness.metrics.get(key).and_then(Value::as_str)
}
