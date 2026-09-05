//! Selected and withheld backend routing outcomes with explicit regime bias.

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    widgets::{Cell, Row, Table},
};

use crate::app::App;
use crate::backend_cohort::CohortWithheldIntent;
use crate::cohort_format::{eastern_time, fill_time};
use crate::cohort_widgets::{WIDE_WIDTH, panel, provider_alias, render_empty};

pub(super) fn render_actions(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort.actions.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " SELECTED BACKEND ACTIONS // CURRENT RUN ",
            "0 action records in retained window\nSetup blockers remain visible above until a provider emits an eligible intent",
        );
        return;
    }
    if area.width >= WIDE_WIDTH {
        render_wide_actions(frame, app, area);
    } else {
        render_compact_actions(frame, app, area);
    }
}

fn render_compact_actions(frame: &mut Frame, app: &App, area: Rect) {
    let rows = app.backend.cohort.actions.iter().rev().map(|action| {
        Row::new(vec![
            Cell::from(eastern_time(&action.observed_at)),
            Cell::from(action.action.to_uppercase()).style(app.theme.bull),
            Cell::from(action.symbol.as_str()).style(app.theme.title),
            Cell::from(action.side.to_uppercase()),
            Cell::from(provider_alias(&action.strategy_id)),
            Cell::from(regime_bias(
                action.regime_alignment_score,
                action.regime_alignment_stance.as_deref(),
            )),
            Cell::from(format!("${:.4}", action.reference_price)),
        ])
    });
    render_action_table(frame, app, area, rows, false);
}

fn render_wide_actions(frame: &mut Frame, app: &App, area: Rect) {
    let rows = app.backend.cohort.actions.iter().rev().map(|action| {
        Row::new(vec![
            Cell::from(eastern_time(&action.observed_at)),
            Cell::from(action.action.to_uppercase()).style(app.theme.bull),
            Cell::from(action.symbol.as_str()).style(app.theme.title),
            Cell::from(action.side.to_uppercase()),
            Cell::from(provider_alias(&action.strategy_id)),
            Cell::from(action.decision_time_ms.to_string()),
            Cell::from(regime_bias(
                action.regime_alignment_score,
                action.regime_alignment_stance.as_deref(),
            )),
            Cell::from(format!("${:.4}", action.reference_price)),
        ])
    });
    render_action_table(frame, app, area, rows, true);
}

fn render_action_table<'a, I>(frame: &mut Frame, app: &App, area: Rect, rows: I, wide: bool)
where
    I: Iterator<Item = Row<'a>>,
{
    let widths = if wide {
        vec![12, 10, 13, 8, 34, 18, 25, 13]
    } else {
        vec![12, 9, 13, 7, 18, 25, 12]
    }
    .into_iter()
    .map(Constraint::Length);
    let headers = if wide {
        vec![
            "TIME ET",
            "ACTION",
            "COIN",
            "SIDE",
            "PROVIDER",
            "DECISION MS",
            "ROUTE BIAS",
            "REFERENCE",
        ]
    } else {
        vec![
            "TIME ET",
            "ACTION",
            "COIN",
            "SIDE",
            "PROVIDER",
            "ROUTE BIAS",
            "REFERENCE",
        ]
    };
    let table = Table::new(rows, widths)
        .column_spacing(1)
        .header(Row::new(headers).style(app.theme.header))
        .block(panel(" SELECTED BACKEND ACTIONS // RECENT 50 ", app));
    frame.render_widget(table, area);
}

pub(super) fn render_withheld(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort.withheld.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " WITHHELD INTENTS // CURRENT RUN // NOTHING HIDDEN ",
            "0 withheld intent records in retained window\nWithholding begins only after an eligible intent reaches the router",
        );
        return;
    }
    let wide = area.width >= WIDE_WIDTH;
    let rows = app
        .backend
        .cohort
        .withheld
        .iter()
        .rev()
        .map(|intent| withheld_row(intent, app));
    let table = Table::new(rows, withheld_widths(wide))
        .column_spacing(1)
        .header(
            Row::new([
                "ARRIVAL ET",
                "DECISION ET",
                "COIN",
                "SIDE",
                "PROVIDER",
                "WITHHELD REASON",
                "REGIME / SOURCE EVIDENCE",
            ])
            .style(app.theme.header),
        )
        .block(panel(
            " WITHHELD INTENTS // CURRENT RUN // NOTHING HIDDEN // RECENT 50 ",
            app,
        ));
    frame.render_widget(table, area);
}

fn withheld_row<'a>(intent: &'a CohortWithheldIntent, app: &App) -> Row<'a> {
    let provider = provider_alias(&intent.strategy_id);
    Row::new(vec![
        Cell::from(eastern_time(&intent.observed_at)),
        Cell::from(fill_time(intent.decision_time_ms)),
        Cell::from(intent.symbol.as_str()).style(app.theme.title),
        Cell::from(intent.side.to_uppercase()),
        Cell::from(provider),
        Cell::from(intent.reason.as_str()).style(app.theme.gold),
        Cell::from(format!(
            "{} // {}",
            regime_bias(
                intent.regime_alignment_score,
                intent.regime_alignment_stance.as_deref(),
            ),
            intent.source_reason,
        )),
    ])
}

fn regime_bias(score: Option<f64>, stance: Option<&str>) -> String {
    let Some(value) = score else {
        return "REGIME BIAS N/A".into();
    };
    let label = match stance {
        Some("directionally_supported") => "SUPPORT",
        Some("directionally_opposed") => "OPPOSE",
        Some("mixed_or_transition") => "MIXED",
        _ => "INVALID",
    };
    format!("REGIME BIAS {value:+.2} {label}")
}

fn withheld_widths(wide: bool) -> [Constraint; 7] {
    if wide {
        [
            Constraint::Length(12),
            Constraint::Length(12),
            Constraint::Length(13),
            Constraint::Length(8),
            Constraint::Length(34),
            Constraint::Percentage(28),
            Constraint::Min(20),
        ]
    } else {
        [
            Constraint::Length(12),
            Constraint::Length(12),
            Constraint::Length(13),
            Constraint::Length(7),
            Constraint::Length(18),
            Constraint::Percentage(34),
            Constraint::Min(18),
        ]
    }
}
