//! Report-only regime-routing conflict scorecard.

use ratatui::{
    Frame,
    layout::Rect,
    text::{Line, Span},
    widgets::Paragraph,
};

use crate::app::App;
use crate::backend_cohort_regime_conflicts::{
    CohortRegimeConflictEvidence, CohortRegimeConflictHorizon,
};
use crate::cohort_widgets::panel;

/// Render causal regime-versus-static routing evidence without execution authority.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let mut lines = app
        .backend
        .cohort_checkpoint
        .regime_conflicts
        .as_ref()
        .map_or_else(
            || unavailable_lines(app),
            |value| evidence_lines(app, value, area.width),
        );
    lines.push(coverage_line(app));
    lines.push(timer_line(app));
    lines.push(aligned_timer_line(app));
    frame.render_widget(
        Paragraph::new(lines).block(panel(" ROUTING ARBITRATION // COUNTERFACTUAL ", app)),
        area,
    );
}

fn unavailable_lines(app: &App) -> Vec<Line<'static>> {
    vec![
        Line::from(Span::styled("JOURNAL N/A", app.theme.muted)),
        Line::from("REPORT ONLY // AUTHORITY NONE"),
        Line::from("AWAITING POST-ACTIVATION CONFLICTS"),
    ]
}

fn evidence_lines<'a>(
    app: &'a App,
    value: &'a CohortRegimeConflictEvidence,
    width: u16,
) -> Vec<Line<'a>> {
    let mut lines = vec![
        state_line(app, value),
        Line::from(format!(
            "CONFLICT {}  CHANGED {}  COMP {}  SAME {}",
            value.conflicts,
            value.changed_static_choice,
            value.directionally_comparable,
            value.same_direction_provider_only,
        )),
    ];
    lines.extend(horizon_lines(app, value.five_minute.as_ref(), width));
    lines.push(Line::from(Span::styled(
        "REPORT ONLY // AUTHORITY NONE",
        app.theme.muted,
    )));
    lines
}

fn coverage_line(app: &App) -> Line<'static> {
    let checkpoint = &app.backend.cohort_checkpoint;
    let evaluations = count(checkpoint.forward_evaluations);
    let resolved = count(checkpoint.five_minute_paths_resolved);
    let independent = count(checkpoint.five_minute_paths_independent);
    let coverage = match checkpoint.forward_path_coverage_complete {
        Some(true) => "OK",
        Some(false) => "GAP",
        None => "N/A",
    };
    Line::from(format!(
        "FWD {evaluations} // 5M {resolved}/{independent} // COV {coverage}"
    ))
}

fn timer_line(app: &App) -> Line<'static> {
    let Some(value) = &app.backend.cohort_checkpoint.timer_context_evidence else {
        return Line::from("TIMER EXIT CONTEXT N/A | CHG N/A");
    };
    let challenger = match (
        value.challenger_extend,
        value.challenger_exit,
        value.challenger_abstain,
    ) {
        (Some(extend), Some(exit), Some(abstain)) => {
            format!("K{extend}/EXIT{exit}/W{abstain}")
        }
        _ => "CHALLENGER N/A".into(),
    };
    Line::from(format!(
        "TMR{} P{} S{}/O{}/M{}/U{} {}",
        value.timer_exits,
        value.provider_symbols.len(),
        value.still_directionally_supported,
        value.directionally_opposed,
        value.mixed_or_transition,
        value.unavailable,
        challenger,
    ))
}

fn aligned_timer_line(app: &App) -> Line<'static> {
    let Some(value) = app
        .backend
        .cohort_checkpoint
        .timer_context_evidence
        .as_ref()
        .and_then(|timer| timer.aligned_zero_opposition_five_minute.as_ref())
    else {
        return Line::from(Span::styled("ALN0P 5M N/A", app.theme.muted));
    };
    let style = if value.incremental_gross_pnl_usd > 0.0 {
        app.theme.bull
    } else if value.incremental_gross_pnl_usd < 0.0 {
        app.theme.bear
    } else {
        app.theme.gold
    };
    Line::from(Span::styled(
        format!(
            "ALN0P 5M E{} R{} +{}/-{} ST{} ΔG {:+.2}",
            value.eligible,
            value.resolved,
            value.positive,
            value.negative,
            value.protective_stop_hits,
            value.incremental_gross_pnl_usd,
        ),
        style,
    ))
}

fn count(value: Option<usize>) -> String {
    value.map_or_else(|| "N/A".into(), |number| number.to_string())
}

fn state_line<'a>(app: &'a App, value: &'a CohortRegimeConflictEvidence) -> Line<'a> {
    let style = if value.state == "active" {
        app.theme.cyan
    } else {
        app.theme.gold
    };
    Line::from(vec![
        Span::styled(value.state.replace('_', " ").to_uppercase(), style),
        Span::raw("  //  "),
        Span::styled(
            value.evidence_state.replace('_', " ").to_uppercase(),
            app.theme.muted,
        ),
    ])
}

fn horizon_lines<'a>(
    app: &'a App,
    horizon: Option<&CohortRegimeConflictHorizon>,
    width: u16,
) -> Vec<Line<'a>> {
    let Some(value) = horizon else {
        return vec![
            Line::from("5M PATHS N/A"),
            Line::from("REGIME/STATIC EDGE N/A"),
        ];
    };
    let advantage = value
        .mean_advantage_bps
        .map_or_else(|| "N/A".into(), |number| format!("{number:+.2}bps"));
    if width < 50 {
        return vec![
            Line::from(format!(
                "5M R/I {}/{} C{} M{}",
                value.resolved, value.independent, value.censored, value.missing_data
            )),
            Line::from(Span::styled(
                format!(
                    "R/S/T {}/{}/{}  Δ {advantage}",
                    value.regime_wins, value.static_wins, value.ties
                ),
                advantage_style(app, value.mean_advantage_bps),
            )),
        ];
    }
    vec![
        Line::from(format!(
            "5M RESOLVED {}  INDEP {}  CENS {}  MISS {}",
            value.resolved, value.independent, value.censored, value.missing_data
        )),
        Line::from(Span::styled(
            format!(
                "REGIME {}  STATIC {}  TIE {}  ADV {advantage}",
                value.regime_wins, value.static_wins, value.ties
            ),
            advantage_style(app, value.mean_advantage_bps),
        )),
    ]
}

fn advantage_style(app: &App, value: Option<f64>) -> ratatui::style::Style {
    match value {
        Some(number) if number > 0.0 => app.theme.bull,
        Some(number) if number < 0.0 => app.theme.bear,
        Some(_) => app.theme.gold,
        None => app.theme.muted,
    }
}
