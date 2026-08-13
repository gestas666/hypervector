//! Focused read-only chart and provider evidence for one cohort coin.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Clear, Paragraph, Wrap},
};

use crate::app::App;
use crate::backend_cohort::{CohortProvider, CohortProviderEvaluation};
use crate::cohort_format::fill_time;
use crate::cohort_router_format::human_token;
use crate::cohort_widgets::{panel, provider_alias, provider_identity_label, render_empty};

/// Render the selected coin's enlarged candles and exact strategy evidence.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let Some(symbol) = app.selected_cohort_symbol() else {
        return;
    };
    let modal = centered_rect(98, 94, area);
    frame.render_widget(Clear, modal);
    let block = panel(
        format!(" {symbol} STRATEGY CHART // BACKEND EVIDENCE "),
        app,
    );
    let inner = block.inner(modal);
    frame.render_widget(block, modal);
    let timeframe = selected_provider(app, symbol)
        .map(|provider| provider.timeframe.as_str())
        .unwrap_or("N/A");
    let rows = Layout::vertical([Constraint::Length(2), Constraint::Min(12)]).split(inner);
    frame.render_widget(Paragraph::new(header(app, symbol, timeframe)), rows[0]);
    let columns =
        Layout::horizontal([Constraint::Percentage(61), Constraint::Percentage(39)]).split(rows[1]);
    crate::cohort_chart::render_focused(frame, app, columns[0], symbol, timeframe);
    render_provider(frame, app, columns[1], symbol);
}

fn header(app: &App, symbol: &str, timeframe: &str) -> Vec<Line<'static>> {
    let provider_count = app
        .backend
        .cohort
        .providers
        .iter()
        .filter(|provider| provider.symbols.iter().any(|value| value == symbol))
        .count();
    let source = if timeframe == "1m" {
        "BACKEND COMPLETED BARS".to_string()
    } else {
        format!(
            "AGGREGATED FROM BACKEND COMPLETED 1M  //  INCOMPLETE {} EXCLUDED",
            timeframe.to_uppercase()
        )
    };
    vec![
        Line::from(vec![
            Span::styled(format!("VIEW {}", timeframe.to_uppercase()), app.theme.cyan),
            Span::raw(format!(" // {source} // {provider_count} STRATEGY VIEW(S)")),
        ]),
        Line::from(Span::styled(
            "[↑/↓] STRATEGY  //  [Enter/Esc] CLOSE  //  DISPLAY ONLY",
            app.theme.muted,
        )),
    ]
}

fn selected_provider<'a>(app: &'a App, symbol: &str) -> Option<&'a CohortProvider> {
    app.backend
        .cohort
        .providers
        .get(app.selected_cohort_chart_provider_index)
        .filter(|provider| provider.symbols.iter().any(|value| value == symbol))
}

fn render_provider(frame: &mut Frame, app: &App, area: Rect, symbol: &str) {
    let Some(provider) = selected_provider(app, symbol) else {
        render_empty(
            frame,
            app,
            area,
            " STRATEGY EVIDENCE ",
            "CONFIGURED PROVIDER UNAVAILABLE",
        );
        return;
    };
    let evaluation = latest_evaluation(app, provider, symbol);
    let lines = provider_lines(provider, evaluation, app);
    frame.render_widget(
        Paragraph::new(lines).wrap(Wrap { trim: true }).block(panel(
            format!(
                " {} // DECISION TF {} ",
                provider_alias(&provider.strategy_id),
                provider.timeframe.to_uppercase()
            ),
            app,
        )),
        area,
    );
}

fn latest_evaluation<'a>(
    app: &'a App,
    provider: &CohortProvider,
    symbol: &str,
) -> Option<&'a CohortProviderEvaluation> {
    app.backend.cohort.evaluations.iter().find(|evaluation| {
        evaluation.strategy_id == provider.strategy_id && evaluation.symbol == symbol
    })
}

fn provider_lines(
    provider: &CohortProvider,
    evaluation: Option<&CohortProviderEvaluation>,
    app: &App,
) -> Vec<Line<'static>> {
    let Some(value) = evaluation else {
        return vec![
            Line::from(provider_identity_label(&provider.strategy_id)),
            Line::from("LATEST DECISION UNAVAILABLE"),
            Line::from("INDICATORS UNAVAILABLE FOR THIS LEDGER WINDOW"),
        ];
    };
    let mut lines = decision_lines(value, app);
    lines.insert(
        0,
        Line::from("EXECUTION EVENT-DRIVEN AFTER CLOSED DECISION"),
    );
    lines.extend(indicator_lines(value, app));
    lines.extend(provenance_lines(value, provider, app));
    lines
}

fn decision_lines(value: &CohortProviderEvaluation, app: &App) -> Vec<Line<'static>> {
    let readiness = &value.readiness;
    vec![
        Line::from(format!(
            "DECISION {} // ELIGIBLE {}",
            value.decision_action.to_uppercase(),
            if value.eligible { "YES" } else { "NO" }
        )),
        Line::from(format!(
            "AT {} // SIDE {}",
            fill_time(value.decision_time_ms),
            optional(value.side.as_deref()).to_uppercase()
        )),
        Line::from(format!(
            "REGIME 1M {} // 5M {} // 15M {}",
            optional(value.state_1m.as_deref()),
            optional(
                value
                    .state_5m
                    .as_deref()
                    .or(value.primary_regime.as_deref())
            ),
            optional(value.context_15m.as_deref()),
        )),
        Line::from(vec![
            Span::raw(format!(
                "READINESS {:.1}% // {}/{} ",
                readiness.readiness_fraction * 100.0,
                readiness.conditions_met,
                readiness.conditions_required,
            )),
            Span::styled(
                readiness_meter(readiness.readiness_fraction),
                app.theme.gold,
            ),
        ]),
        Line::from(format!("REASON {}", human_token(&value.reason))),
    ]
}

fn indicator_lines(value: &CohortProviderEvaluation, app: &App) -> Vec<Line<'static>> {
    vec![
        Line::from(""),
        Line::from(Span::styled("LIVE STRATEGY INDICATORS", app.theme.cyan)),
        Line::from(if value.readiness.indicators.is_empty() {
            "UNAVAILABLE".into()
        } else {
            value.readiness.indicators.join("  ·  ")
        }),
        Line::from(""),
        Line::from(Span::styled("NEXT BLOCKERS", app.theme.gold)),
        Line::from(if value.readiness.blockers.is_empty() {
            "NONE REPORTED".into()
        } else {
            value
                .readiness
                .blockers
                .iter()
                .map(|blocker| human_token(blocker))
                .collect::<Vec<_>>()
                .join("  ·  ")
        }),
    ]
}

fn provenance_lines(
    value: &CohortProviderEvaluation,
    provider: &CohortProvider,
    app: &App,
) -> Vec<Line<'static>> {
    let metrics = &value.readiness.metrics;
    let component = text_metric(metrics.get("component_provenance"));
    let authority = text_metric(metrics.get("component_authority"));
    let evidence =
        app.backend.cohort.strategy_evidence.iter().find(|record| {
            record.strategy_id == value.strategy_id && record.symbol == value.symbol
        });
    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled("PROVENANCE", app.theme.cyan)),
        Line::from(format!(
            "SOURCE {}",
            evidence.map_or("N/A", |record| record.evidence_source.as_str())
        )),
        Line::from(format!("COMPONENT {component} // AUTHORITY {authority}")),
        Line::from(format!(
            "EFFECT {}",
            evidence.map_or("N/A", |record| record.execution_effect.as_str())
        )),
    ];
    if let Some(profile) = provider.source_profile.as_deref() {
        lines.push(Line::from(format!("PROFILE {profile}")));
    }
    lines
}

fn text_metric(value: Option<&serde_json::Value>) -> &str {
    value.and_then(serde_json::Value::as_str).unwrap_or("N/A")
}

fn optional(value: Option<&str>) -> &str {
    value.filter(|item| !item.is_empty()).unwrap_or("N/A")
}

fn readiness_meter(value: f64) -> String {
    let filled = (value.clamp(0.0, 1.0) * 10.0).round() as usize;
    format!("{}{}", "■".repeat(filled), "·".repeat(10 - filled))
}

fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(area);
    Layout::horizontal([
        Constraint::Percentage((100 - percent_x) / 2),
        Constraint::Percentage(percent_x),
        Constraint::Percentage((100 - percent_x) / 2),
    ])
    .split(vertical[1])[1]
}
