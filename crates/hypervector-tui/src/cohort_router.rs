//! Read-only intent selection and withholding view for the shared cohort.

#[path = "cohort_router_outcomes.rs"]
mod outcomes;

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Cell, Paragraph, Row, Table, TableState, Wrap},
};

use crate::app::App;
use crate::backend_cohort::CohortProviderEvaluation;
use crate::cohort_format::{eastern_time, fill_time};
use crate::cohort_route_authority::{provider_route_label, provider_route_token};
use crate::cohort_router_format::human_token;
use crate::cohort_widgets::{WIDE_WIDTH, panel, provider_alias, render_empty};

const HULK_STRATEGY_ID: &str = "hulk_expansion_bidirectional_tuned_v2";

/// Render recent selected actions and every visible withholding reason.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let desired_readiness = if app.backend.cohort.evaluations.is_empty() {
        5
    } else {
        app.backend.cohort.evaluations.len() as u16 + 8
    };
    let readiness_height = desired_readiness.min(area.height.saturating_sub(11).max(5));
    let remaining_height = area.height.saturating_sub(3 + readiness_height);
    let actions_height = remaining_height / 2;
    let withheld_height = remaining_height.saturating_sub(actions_height);
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Length(readiness_height),
            Constraint::Length(actions_height),
            Constraint::Length(withheld_height),
        ])
        .split(area);
    render_summary(frame, app, sections[0]);
    render_evaluations(frame, app, sections[1]);
    outcomes::render_actions(frame, app, sections[2]);
    outcomes::render_withheld(frame, app, sections[3]);
}

fn render_summary(frame: &mut Frame, app: &App, area: Rect) {
    let account = app.backend.cohort.account.as_ref();
    let open = account.map_or(0, |value| value.open_position_count);
    let maximum = app.backend.cohort.maximum_concurrent_positions;
    let asset_count = app.backend.cohort.enabled_symbols.len();
    let routing = routing_contract(app, area.width);
    let (coverage, coverage_style) = setup_coverage(app);
    let line = Line::from(vec![
        Span::styled(
            format!("ROUTED {}", app.backend.cohort.actions.len()),
            app.theme.bull,
        ),
        Span::raw("        "),
        Span::styled(
            format!("WITHHELD {}", app.backend.cohort.withheld.len()),
            app.theme.gold,
        ),
        Span::raw("        "),
        Span::styled(coverage, coverage_style),
        Span::raw("        "),
        Span::styled(format!("SLOTS {open} / {maximum}"), app.theme.cyan),
        Span::raw(format!(
            "        ASSETS {asset_count}        ONE POSITION PER COIN        {routing}"
        )),
    ]);
    frame.render_widget(
        Paragraph::new(line)
            .centered()
            .block(panel(" RECENT ROUTING WINDOW ", app)),
        area,
    );
}

fn setup_coverage(app: &App) -> (String, ratatui::style::Style) {
    let Some(coverage) = app.backend.cohort.setup_coverage.as_ref() else {
        return (
            format!(
                "EVALUATED {} // SETUPS ?",
                app.backend.cohort.evaluations.len()
            ),
            app.theme.muted,
        );
    };
    if coverage.complete {
        return (
            format!(
                "SETUPS {}/{} // COMPLETE",
                coverage.observed_provider_symbols, coverage.expected_provider_symbols
            ),
            app.theme.bull,
        );
    }
    (
        format!(
            "SETUPS {}/{} // MISSING {}",
            coverage.observed_provider_symbols,
            coverage.expected_provider_symbols,
            coverage.missing_provider_symbols.len()
        ),
        app.theme.bear,
    )
}

fn routing_contract(app: &App, width: u16) -> &'static str {
    if app.backend.cohort.routing_policy.is_none() {
        return "ROUTE POLICY N/A";
    }
    if width >= 160 {
        "CONFLICT REGIME PREF // LONE UNGATED // FORCED EXIT OFF"
    } else {
        "REGIME PREF // LONE UNGATED"
    }
}

fn render_evaluations(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort.evaluations.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " SETUP READINESS // DIAGNOSTIC, NOT WIN PROBABILITY ",
            "Awaiting the first completed backend provider evaluation",
        );
        return;
    }
    let wide = area.width >= WIDE_WIDTH;
    let table_height =
        (app.backend.cohort.evaluations.len() as u16 + 3).min(area.height.saturating_sub(5));
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(table_height), Constraint::Min(5)])
        .split(area);
    let rows = app
        .backend
        .cohort
        .evaluations
        .iter()
        .map(|evaluation| evaluation_row(evaluation, app, wide));
    let table = Table::new(rows, evaluation_widths(wide))
        .column_spacing(1)
        .header(evaluation_header(wide).style(app.theme.header))
        .row_highlight_style(app.theme.highlight)
        .highlight_symbol("▸")
        .block(panel(
            " SETUP READINESS // DIAGNOSTIC, NOT WIN PROBABILITY ",
            app,
        ));
    let selected = app
        .selected_cohort_setup_index
        .min(app.backend.cohort.evaluations.len().saturating_sub(1));
    let mut state = TableState::default().with_selected(Some(selected));
    frame.render_stateful_widget(table, sections[0], &mut state);
    render_leading_setup(frame, app, sections[1]);
}

fn evaluation_row<'a>(evaluation: &'a CohortProviderEvaluation, app: &App, wide: bool) -> Row<'a> {
    let provider = format!(
        "{} [{}]",
        provider_alias(&evaluation.strategy_id),
        provider_route_token(
            &app.backend.cohort.providers,
            &evaluation.strategy_id,
            &evaluation.symbol,
            app.backend.live_armed,
        )
    );
    let progress = readiness_bar(evaluation.readiness.readiness_fraction);
    let conditions = format!(
        "{}/{}",
        evaluation.readiness.conditions_met, evaluation.readiness.conditions_required
    );
    let status = evaluation_status(evaluation);
    let indicators = evaluation.readiness.indicators.join(" · ");
    let blockers = human_blockers(evaluation);
    let style = if evaluation.eligible {
        app.theme.bull
    } else if evaluation.readiness.readiness_fraction >= 0.8 {
        app.theme.gold
    } else {
        app.theme.muted
    };
    if wide {
        Row::new(vec![
            Cell::from(eastern_time(&evaluation.observed_at)),
            Cell::from(fill_time(evaluation.decision_time_ms)),
            Cell::from(evaluation.symbol.as_str()).style(app.theme.title),
            Cell::from(provider),
            Cell::from(evaluation.side.as_deref().unwrap_or("--").to_uppercase()),
            Cell::from(progress).style(style),
            Cell::from(conditions),
            Cell::from(status),
            Cell::from(indicators),
            Cell::from(blockers).style(app.theme.gold),
        ])
    } else {
        Row::new(vec![
            Cell::from(evaluation.symbol.as_str()).style(app.theme.title),
            Cell::from(provider),
            Cell::from(evaluation.side.as_deref().unwrap_or("--").to_uppercase()),
            Cell::from(progress).style(style),
            Cell::from(conditions),
            Cell::from(compact_evaluation_status(evaluation)),
            Cell::from(blockers).style(app.theme.gold),
        ])
    }
}

fn readiness_bar(fraction: f64) -> String {
    const WIDTH: usize = 8;
    let filled = (fraction * WIDTH as f64).round() as usize;
    format!(
        "{}{} {:>3.0}%",
        "█".repeat(filled.min(WIDTH)),
        "░".repeat(WIDTH.saturating_sub(filled)),
        fraction * 100.0
    )
}

fn evaluation_status(evaluation: &CohortProviderEvaluation) -> String {
    if let Some(reason) = evaluation.backend_non_action_reason.as_deref() {
        return format!("READINESS ONLY · {}", human_token(reason));
    }
    let reason = human_token(&evaluation.reason);
    match (evaluation.score, evaluation.minimum_score) {
        (Some(score), Some(required)) => format!(
            "{} {score}/{required} · {reason}",
            evaluation.decision_action.to_uppercase(),
        ),
        _ => format!(
            "{} {} {} · {reason}",
            evaluation.decision_action.to_uppercase(),
            evaluation.primary_regime.as_deref().unwrap_or("--"),
            evaluation
                .confidence
                .map_or_else(|| "--".into(), |value| format!("{:.0}%", value * 100.0))
        ),
    }
}

fn compact_evaluation_status(evaluation: &CohortProviderEvaluation) -> String {
    if let Some(reason) = evaluation.backend_non_action_reason.as_deref() {
        return format!("READINESS ONLY · {}", human_token(reason));
    }
    let action = evaluation.decision_action.to_uppercase();
    match (evaluation.score, evaluation.minimum_score) {
        (Some(score), Some(required)) => format!("{action} · {score}/{required}"),
        _ => format!(
            "{action} · {} · {}",
            evaluation.primary_regime.as_deref().unwrap_or("--"),
            evaluation
                .confidence
                .map_or_else(|| "--".into(), |value| format!("{:.0}%", value * 100.0))
        ),
    }
}

fn human_blockers(evaluation: &CohortProviderEvaluation) -> String {
    if evaluation.readiness.blockers.is_empty() {
        "NONE".into()
    } else {
        let gaps = evaluation
            .readiness
            .blockers
            .iter()
            .map(|value| human_token(value))
            .collect::<Vec<_>>()
            .join(" · ");
        if is_eligible_hulk(evaluation) {
            format!("SUPPORT ONLY · {gaps}")
        } else {
            gaps
        }
    }
}

fn is_eligible_hulk(evaluation: &CohortProviderEvaluation) -> bool {
    evaluation.strategy_id == HULK_STRATEGY_ID && evaluation.eligible
}

fn leading_gaps(evaluation: &CohortProviderEvaluation) -> String {
    if evaluation.readiness.blockers.is_empty() {
        return "NONE".into();
    }
    let gaps = evaluation.readiness.blockers.join(" · ");
    if is_eligible_hulk(evaluation) {
        format!("SUPPORT ONLY · {gaps}")
    } else {
        gaps
    }
}

fn evaluation_header(wide: bool) -> Row<'static> {
    if wide {
        Row::new([
            "ARRIVAL ET",
            "DECISION ET",
            "COIN",
            "PROVIDER [AUTH]",
            "BIAS",
            "READINESS",
            "MET",
            "SIGNAL / WHY",
            "LIVE INDICATORS",
            "NEXT GAPS",
        ])
    } else {
        Row::new([
            "COIN",
            "PROVIDER [AUTH]",
            "BIAS",
            "READINESS",
            "MET",
            "SIGNAL / WHY",
            "NEXT GAPS",
        ])
    }
}

fn evaluation_widths(wide: bool) -> Vec<Constraint> {
    if wide {
        vec![
            Constraint::Length(12),
            Constraint::Length(12),
            Constraint::Length(12),
            Constraint::Length(23),
            Constraint::Length(5),
            Constraint::Length(13),
            Constraint::Length(5),
            Constraint::Length(24),
            Constraint::Length(28),
            Constraint::Min(25),
        ]
    } else {
        vec![
            Constraint::Length(12),
            Constraint::Length(23),
            Constraint::Length(5),
            Constraint::Length(13),
            Constraint::Length(5),
            Constraint::Length(24),
            Constraint::Min(27),
        ]
    }
}

fn render_leading_setup(frame: &mut Frame, app: &App, area: Rect) {
    let Some(leading) = leading_evaluation(&app.backend.cohort.evaluations) else {
        return;
    };
    let header = format!(
        "{} · {} · ROUTE {} · {} · {:.0}% ({}/{}) · {}",
        leading.symbol,
        provider_alias(&leading.strategy_id),
        provider_route_label(
            &app.backend.cohort.providers,
            &leading.strategy_id,
            &leading.symbol,
            app.backend.live_armed,
        ),
        leading.side.as_deref().unwrap_or("--").to_uppercase(),
        leading.readiness.readiness_fraction * 100.0,
        leading.readiness.conditions_met,
        leading.readiness.conditions_required,
        evaluation_status(leading),
    );
    let lines = vec![
        Line::from(Span::styled(header, app.theme.title)),
        Line::from(format!(
            "INDICATORS  {}",
            leading.readiness.indicators.join(" · ")
        )),
        Line::from(format!(
            "{:<11}{}  //  SOURCE REASON {}",
            if is_eligible_hulk(leading) {
                "SUPPORT"
            } else {
                "BLOCKERS"
            },
            leading_gaps(leading),
            leading.reason,
        )),
    ];
    frame.render_widget(
        Paragraph::new(lines).wrap(Wrap { trim: true }).block(panel(
            " LEADING SETUP // HIGHEST PREREQUISITE COMPLETION ",
            app,
        )),
        area,
    );
}

fn leading_evaluation(
    evaluations: &[CohortProviderEvaluation],
) -> Option<&CohortProviderEvaluation> {
    evaluations.iter().max_by(|left, right| {
        left.eligible
            .cmp(&right.eligible)
            .then_with(|| {
                left.readiness
                    .readiness_fraction
                    .total_cmp(&right.readiness.readiness_fraction)
            })
            .then_with(|| {
                left.readiness
                    .conditions_met
                    .cmp(&right.readiness.conditions_met)
            })
            .then_with(|| left.decision_time_ms.cmp(&right.decision_time_ms))
    })
}
