//! Selected-route setup, execution, risk, timing, and blocker summary.

use ratatui::{
    Frame,
    layout::Rect,
    text::{Line, Span},
    widgets::{Paragraph, Wrap},
};

use crate::app::App;
use crate::backend_cohort::CohortProviderEvaluation;
use crate::cohort_route_authority::provider_route_label;
use crate::cohort_route_contract::{execution_label, risk_label, timing_label};
use crate::cohort_router::{evaluation_bias, evaluation_status, is_eligible_hulk};
use crate::cohort_widgets::{panel, provider_alias};

/// Render the selected route without hiding its configured risk contract.
pub(crate) fn render(frame: &mut Frame, app: &App, selected: usize, area: Rect, wide: bool) {
    let Some(evaluation) = app.backend.cohort.evaluations.get(selected) else {
        return;
    };
    let title = format!(
        " SELECTED SETUP // ROW {}/{} // UP/DOWN CHANGE // ENTER INSPECT ",
        selected + 1,
        app.backend.cohort.evaluations.len(),
    );
    frame.render_widget(
        Paragraph::new(selected_setup_lines(evaluation, app, wide))
            .wrap(Wrap { trim: true })
            .block(panel(title.as_str(), app)),
        area,
    );
}

fn selected_setup_lines(
    evaluation: &CohortProviderEvaluation,
    app: &App,
    wide: bool,
) -> Vec<Line<'static>> {
    let mut lines = vec![
        Line::from(Span::styled(
            selected_header(evaluation, app),
            app.theme.title,
        )),
        Line::from(selected_plan(evaluation, app, wide)),
        Line::from(format!(
            "INDICATORS  {}",
            selected_indicator_summary(evaluation)
        )),
        Line::from(timing_label(evaluation)),
    ];
    if wide {
        lines.insert(
            2,
            Line::from(risk_label(
                evaluation,
                &app.backend.cohort.providers,
                &app.backend.cohort.asset_configs,
            )),
        );
    }
    lines.push(Line::from(blocker_summary(evaluation)));
    lines
}

fn selected_header(evaluation: &CohortProviderEvaluation, app: &App) -> String {
    format!(
        "{} · {} · ROUTE {} · {} · {:.0}% ({}/{}) · {}",
        evaluation.symbol,
        provider_alias(&evaluation.strategy_id),
        provider_route_label(
            &app.backend.cohort.providers,
            &evaluation.strategy_id,
            &evaluation.symbol,
            app.backend.live_armed,
        ),
        evaluation_bias(evaluation, &app.backend.cohort.providers),
        evaluation.readiness.readiness_fraction * 100.0,
        evaluation.readiness.conditions_met,
        evaluation.readiness.conditions_required,
        evaluation_status(evaluation),
    )
}

fn selected_plan(evaluation: &CohortProviderEvaluation, app: &App, wide: bool) -> String {
    let mut plan = execution_label(evaluation, &app.backend.cohort.providers);
    if !wide {
        plan.push_str(" · RISK ENTER FOR SIZING");
    }
    plan
}

fn blocker_summary(evaluation: &CohortProviderEvaluation) -> String {
    format!(
        "{:<11}{}  //  SOURCE REASON {}",
        if is_eligible_hulk(evaluation) {
            "SUPPORT"
        } else {
            "BLOCKERS"
        },
        leading_gaps(evaluation),
        evaluation.reason,
    )
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

fn selected_indicator_summary(evaluation: &CohortProviderEvaluation) -> String {
    const VISIBLE_INDICATORS: usize = 6;
    let indicators = &evaluation.readiness.indicators;
    if indicators.is_empty() {
        return "NONE REPORTED".into();
    }
    let mut summary = indicators
        .iter()
        .take(VISIBLE_INDICATORS)
        .map(String::as_str)
        .collect::<Vec<_>>()
        .join(" · ");
    let hidden = indicators.len().saturating_sub(VISIBLE_INDICATORS);
    if hidden > 0 {
        summary.push_str(&format!(" · +{hidden} MORE // ENTER FOR ALL"));
    }
    summary
}
