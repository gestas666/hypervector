//! Rolling research journal and evidence-boundary workspace.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Cell, Clear, Paragraph, Row, Table, TableState, Wrap},
};

use crate::app::App;
use crate::backend_cohort_checkpoint::{
    CohortObserverPathEvidence, CohortObserverProviderEvidence,
};
use crate::backend_cohort_friction_parity::CohortProviderFrictionParity;
use crate::cohort_opportunity_capture::{one_blocker_lines, path_capture_suffix};
use crate::cohort_orderbook_opportunity::orderbook_lines;
use crate::cohort_research_asymmetric as asymmetric;
use crate::cohort_research_audit::{audit_line, routing_line};
use crate::cohort_research_eligible_policy::{
    line_count as eligible_policy_line_count, lines as eligible_policy_lines,
};
use crate::cohort_research_opportunity_matrix::{
    detail_lines as matrix_detail_lines, forward_summary_lines, summary_line,
};
use crate::cohort_research_profit_lock as profit_lock;
use crate::cohort_research_scorecard::scorecard_lines;
use crate::cohort_research_side_composition as side_composition;
use crate::cohort_research_trail::{evidence as post_soft_trail, summary_text as trail_summary};
use crate::cohort_router_format::human_token;
use crate::cohort_widgets::{panel, provider_alias, provider_identity_label, render_empty};

#[path = "cohort_research_friction.rs"]
mod friction;

use friction::{detail_identity, friction_cell, friction_detail, provider_friction};

const HIP3_SYMBOL_COLUMN_WIDTH: u16 = 12;

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let checkpoint = &app.backend.cohort_checkpoint;
    if !checkpoint.available {
        render_unavailable(frame, app, area);
        return;
    }
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(summary_height(app)),
            Constraint::Length(5),
            Constraint::Min(10),
        ])
        .split(area);
    frame.render_widget(
        Paragraph::new(summary_lines(app)).block(panel(" ROLLING EVIDENCE HEALTH ", app)),
        sections[0],
    );
    crate::cohort_hype_l2_observer::render(frame, app, sections[1]);
    render_journal(frame, app, sections[2]);
}

fn render_unavailable(frame: &mut Frame, app: &App, area: Rect) {
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(5), Constraint::Min(6)])
        .split(area);
    crate::cohort_hype_l2_observer::render(frame, app, sections[0]);
    let issue = app
        .backend
        .cohort_checkpoint
        .issue
        .as_deref()
        .unwrap_or("No rolling checkpoint is available");
    render_empty(
        frame,
        app,
        sections[1],
        " RESEARCH JOURNAL // BACKEND CHECKPOINT ",
        issue,
    );
}

fn summary_height(app: &App) -> u16 {
    let checkpoint = &app.backend.cohort_checkpoint;
    let forward_observers = checkpoint
        .execution_opportunity_matrix
        .as_ref()
        .map_or(0, |matrix| {
            usize::from(matrix.forward_challenger.is_some())
                + matrix.supplemental_forward_challengers.len()
        });
    7 + u16::from(checkpoint.live_audit_status.is_some())
        + u16::from(checkpoint.friction_parity.is_some())
        + u16::from(checkpoint.execution_opportunity_matrix.is_some())
        + u16::from(post_soft_trail(checkpoint).is_some())
        + profit_lock::line_count(checkpoint.profit_lock_challenger.as_ref())
        + asymmetric::line_count(checkpoint.asymmetric_forward_observer.as_ref())
        + side_composition::line_count(checkpoint.side_composition.as_ref())
        + u16::try_from(forward_observers).unwrap_or(u16::MAX)
        + checkpoint
            .eligible_policy_forward
            .as_ref()
            .map_or(0, eligible_policy_line_count)
}

fn summary_lines(app: &App) -> Vec<Line<'static>> {
    let checkpoint = &app.backend.cohort_checkpoint;
    let mut lines = vec![
        Line::from(vec![
            Span::raw("MODE "),
            Span::styled(
                checkpoint
                    .analysis_mode
                    .as_deref()
                    .unwrap_or("N/A")
                    .to_uppercase(),
                app.theme.title,
            ),
        ]),
        routing_line(checkpoint),
        Line::from(format!(
            "5M PATHS {} RESOLVED / {} INDEPENDENT  //  COVERAGE {}",
            count(checkpoint.five_minute_paths_resolved),
            count(checkpoint.five_minute_paths_independent),
            yes_no(checkpoint.forward_path_coverage_complete)
        )),
        Line::from(format!(
            "EVIDENCE {}",
            checkpoint
                .evidence_state
                .as_deref()
                .unwrap_or("N/A")
                .replace('_', " ")
                .to_uppercase()
        )),
        Line::from(Span::styled(
            if checkpoint.eligible_signals.unwrap_or(0) == 0 {
                "FIRED-SIGNAL EVIDENCE NONE // SETUP PATHS CANNOT SUBSTITUTE"
            } else {
                "FIRED-SIGNAL EVIDENCE DESCRIPTIVE ONLY // LIVE EDGE UNPROVEN"
            },
            app.theme.gold,
        )),
    ];
    insert_live_health(&mut lines, app);
    append_summary_evidence(&mut lines, app);
    lines
}

fn insert_live_health(lines: &mut Vec<Line<'static>>, app: &App) {
    let checkpoint = &app.backend.cohort_checkpoint;
    if let Some(status) = &checkpoint.live_audit_status {
        lines.insert(2, audit_line(status));
    }
    if let Some(parity) = &checkpoint.friction_parity {
        lines.insert(
            3,
            Line::from(format!(
                "EXECUTION PARITY {}/{} ALIGNED // {} MISMATCH // ENTRY FILLS {}",
                parity.runtime_shape_aligned,
                parity.provider_symbols,
                parity.contract_mismatch,
                parity.provider_symbols_with_entry_fills,
            )),
        );
    }
}

fn append_summary_evidence(lines: &mut Vec<Line<'static>>, app: &App) {
    let checkpoint = &app.backend.cohort_checkpoint;
    lines.extend(summary_line(app));
    lines.extend(forward_summary_lines(app));
    if let Some(evidence) = &checkpoint.eligible_policy_forward {
        lines.extend(eligible_policy_lines(evidence, app));
    }
    if let Some(evidence) = post_soft_trail(checkpoint) {
        lines.push(Line::from(Span::styled(
            trail_summary(evidence),
            app.theme.gold,
        )));
    }
    if let Some(evidence) = &checkpoint.profit_lock_challenger {
        lines.extend(profit_lock::lines(evidence, app));
    }
    if let Some(evidence) = &checkpoint.asymmetric_forward_observer {
        lines.extend(asymmetric::lines(evidence, app));
    }
    if let Some(evidence) = &checkpoint.side_composition {
        lines.extend(side_composition::lines(evidence, app));
    }
}

fn render_journal(frame: &mut Frame, app: &App, area: Rect) {
    let journal = &app.backend.cohort_checkpoint.observer_provider_journal;
    if journal.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " EVIDENCE-CLASS JOURNAL ",
            "No provider path evidence is available for this checkpoint",
        );
        return;
    }
    let rows = journal.iter().map(|item| journal_row(item, app));
    let table = Table::new(
        rows,
        [
            Constraint::Length(18),
            Constraint::Length(HIP3_SYMBOL_COLUMN_WIDTH),
            Constraint::Length(6),
            Constraint::Length(8),
            Constraint::Length(6),
            Constraint::Length(19),
            Constraint::Length(11),
            Constraint::Length(24),
            Constraint::Min(18),
        ],
    )
    .column_spacing(1)
    .header(journal_header(app))
    .row_highlight_style(app.theme.highlight)
    .highlight_symbol("▸ ")
    .block(panel(
        " EVIDENCE-CLASS JOURNAL // NOT FILLS, PNL, OR WIN PROBABILITY ",
        app,
    ));
    let selected = app
        .selected_cohort_journal_index
        .min(journal.len().saturating_sub(1));
    let mut state = TableState::default().with_selected(Some(selected));
    frame.render_stateful_widget(table, area, &mut state);
}

fn journal_header(app: &App) -> Row<'static> {
    Row::new([
        "PROVIDER",
        "COIN",
        "SIDE",
        "SETUP",
        "FIRE",
        "SIGNAL 5M",
        "EXEC",
        "FORWARD STATE",
        "NEXT BLOCKER",
    ])
    .style(app.theme.header)
}

fn journal_row<'a>(item: &'a CohortObserverProviderEvidence, app: &App) -> Row<'a> {
    Row::new(vec![
        Cell::from(provider_alias(&item.strategy_id)).style(app.theme.title),
        Cell::from(item.symbol.as_str()),
        Cell::from(item.latest_side.as_deref().unwrap_or("N/A").to_uppercase()),
        Cell::from(
            item.readiness_fraction
                .map_or_else(|| "N/A".into(), |value| format!("{:.0}%", value * 100.0)),
        ),
        Cell::from(item.eligible_signals.to_string()),
        Cell::from(path_cell(item.eligible_paths.get(&5))),
        friction_cell(app, item),
        Cell::from(
            item.forward_assessment
                .as_deref()
                .map_or_else(|| "NOT REPORTED".into(), human_token),
        ),
        Cell::from(
            item.latest_blockers
                .first()
                .map_or_else(|| "NONE".into(), |value| human_token(value)),
        ),
    ])
}

fn path_cell(value: Option<&CohortObserverPathEvidence>) -> String {
    let Some(path) = value else {
        return "N/A".into();
    };
    if path.resolved == 0 {
        return format!("R0/I0 C{} M{}", path.censored, path.missing_data);
    }
    let mean = path
        .mean_directional_return_bps
        .map_or_else(|| "N/A".into(), |number| format!("{number:+.1}"));
    let positive = path.positive_directional_rate.map_or_else(
        || "N/A".into(),
        |number| format!("{:.0}%", (number * 100.0).round()),
    );
    format!("R{}/I{} {mean} {positive}", path.resolved, path.independent)
}

pub(crate) fn render_detail(frame: &mut Frame, app: &App, area: Rect) {
    let Some(item) = app
        .backend
        .cohort_checkpoint
        .observer_provider_journal
        .get(app.selected_cohort_journal_index)
    else {
        return;
    };
    let modal = centered_rect(90, 82, area);
    frame.render_widget(Clear, modal);
    let friction = provider_friction(app, item);
    frame.render_widget(
        Paragraph::new(detail_lines(item, friction, app))
            .wrap(Wrap { trim: true })
            .block(panel(" RESEARCH EVIDENCE INSPECTOR ", app)),
        modal,
    );
}

fn detail_lines<'a>(
    item: &'a CohortObserverProviderEvidence,
    friction: Option<&'a CohortProviderFrictionParity>,
    app: &App,
) -> Vec<Line<'a>> {
    let mut lines = detail_identity(item, app);
    lines.extend(orderbook_lines(item.orderbook_opportunity.as_ref(), app));
    if let Some(parity) = friction {
        lines.push(Line::from(""));
        lines.extend(friction_detail(parity, app));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "ELIGIBLE SIGNAL PATHS // COUNTERFACTUAL CANDLE PATHS",
        app.theme.cyan,
    )));
    lines.extend(horizon_lines(&item.eligible_paths));
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "READINESS-ONLY PATHS // BLOCKED SETUP ANNOTATIONS",
        app.theme.gold,
    )));
    lines.extend(horizon_lines(&item.readiness_paths));
    lines.extend(one_blocker_lines(
        item.one_blocker_near_misses.as_ref(),
        app,
    ));
    lines.extend(matrix_detail_lines(item, app));
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "PATHS DO NOT CLAIM FILLS, PNL, OR EDGE // [Enter/Esc] CLOSE",
        app.theme.muted,
    )));
    lines
}

fn horizon_lines(
    paths: &std::collections::BTreeMap<u16, CohortObserverPathEvidence>,
) -> Vec<Line<'static>> {
    [5_u16, 15, 30, 60]
        .into_iter()
        .map(|minutes| Line::from(horizon_line(minutes, paths.get(&minutes))))
        .collect()
}

fn horizon_line(minutes: u16, value: Option<&CohortObserverPathEvidence>) -> String {
    let Some(path) = value else {
        return format!("{minutes:>2}M  N/A");
    };
    let mean = path
        .mean_directional_return_bps
        .map_or_else(|| "N/A".into(), |value| format!("{value:+.2}bps"));
    let positive = path
        .positive_directional_rate
        .map_or_else(|| "N/A".into(), |value| format!("{:.1}%", value * 100.0));
    format!(
        "{minutes:>2}M  R{}/I{}  MEAN {mean}  POS {positive}  CENS {}  MISS {}{}",
        path.resolved,
        path.independent,
        path.censored,
        path.missing_data,
        path_capture_suffix(path),
    )
}

fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let rows = Layout::vertical([
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
    .split(rows[1])[1]
}

fn count(value: Option<usize>) -> String {
    value.map_or_else(|| "N/A".into(), |item| item.to_string())
}

fn yes_no(value: Option<bool>) -> &'static str {
    match value {
        Some(true) => "COMPLETE",
        Some(false) => "INCOMPLETE",
        None => "N/A",
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::detail_lines;
    use crate::app::App;
    use crate::backend_cohort_orderbook_opportunity::{
        CohortEligibleSignalContext, CohortProviderOrderbookOpportunity, CohortSignalStanceCounts,
    };
    use crate::cohort_observer_evidence::CohortObserverProviderEvidence;

    #[test]
    fn eligible_signal_context_precedes_long_path_sections() {
        let app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        let item = provider_with_signal_context();
        let lines = detail_lines(&item, None, &app)
            .into_iter()
            .map(|line| {
                line.spans
                    .into_iter()
                    .map(|span| span.content.into_owned())
                    .collect::<String>()
            })
            .collect::<Vec<_>>();
        let context = lines
            .iter()
            .position(|line| line.contains("ELIGIBLE SIGNAL CONTEXT"))
            .expect("signal context rendered");
        let paths = lines
            .iter()
            .position(|line| line.contains("ELIGIBLE SIGNAL PATHS"))
            .expect("path section rendered");

        assert!(
            context < paths,
            "signal context must remain above clipped path detail"
        );
    }

    fn provider_with_signal_context() -> CohortObserverProviderEvidence {
        let counts = CohortSignalStanceCounts {
            aligned: 1,
            neutral: 0,
            opposed: 0,
            unavailable: 0,
        };
        CohortObserverProviderEvidence {
            strategy_id: "provider".into(),
            symbol: "BTC".into(),
            research_state: None,
            confidence: None,
            historical_cadence: None,
            historical_summary: None,
            evidence_source: None,
            directional_research: BTreeMap::new(),
            forward_assessment: None,
            execution_performance_scope: None,
            execution_performance: None,
            execution_performance_by_side: BTreeMap::new(),
            repeatability_evidence: None,
            latest_side: Some("long".into()),
            readiness_fraction: Some(1.0),
            latest_reason: Some("signal".into()),
            latest_blockers: Vec::new(),
            readiness_evaluations: 1,
            eligible_signals: 1,
            paths: BTreeMap::new(),
            eligible_paths: BTreeMap::new(),
            readiness_paths: BTreeMap::new(),
            one_blocker_near_misses: None,
            orderbook_opportunity: Some(CohortProviderOrderbookOpportunity {
                by_blocker: BTreeMap::new(),
                pressure_clock: None,
                eligible_signal_context: Some(CohortEligibleSignalContext {
                    eligible_signals: 1,
                    pressure_stance: counts.clone(),
                    state_5m_stance: counts.clone(),
                    context_15m_stance: counts,
                    executable_bbo_markouts: None,
                }),
            }),
        }
    }
}
