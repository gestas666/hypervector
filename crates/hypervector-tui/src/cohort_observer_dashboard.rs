//! Research journal for the execution-incapable shared-cohort observer.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    widgets::{Cell, Row, Table},
};

use crate::app::App;
use crate::backend_cohort_checkpoint::{
    CohortObserverPathEvidence, CohortObserverProviderEvidence,
};
use crate::cohort_widgets::{panel, provider_alias};

const CHECKPOINT_HEIGHT: u16 = 3;
const MARKET_PULSE_HEIGHT: u16 = 8;
const HORIZONS: [u16; 4] = [5, 15, 30, 60];

/// Render setup progression and counterfactual paths without execution claims.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(CHECKPOINT_HEIGHT),
            Constraint::Length(MARKET_PULSE_HEIGHT),
            Constraint::Min(8),
        ])
        .split(area);
    crate::cohort_checkpoint_widget::render(frame, app, sections[0]);
    crate::cohort_market_pulse::render(frame, app, sections[1]);
    render_path_journal(frame, app, sections[2]);
}

fn render_path_journal(frame: &mut Frame, app: &App, area: Rect) {
    let rows = ordered_journal(app)
        .into_iter()
        .map(|value| path_row(value, app));
    let widths = [5, 17, 9, 20, 20, 20, 20].map(Constraint::Length);
    let table = Table::new(rows, widths)
        .column_spacing(1)
        .header(
            Row::new(["COIN", "PROVIDER", "SEEN/FIRE", "5M", "15M", "30M", "60M"])
                .style(app.theme.header),
        )
        .block(panel(
            " CAUSAL FORWARD PATH JOURNAL // ANNOTATIONS, NOT FILLS OR PNL ",
            app,
        ));
    frame.render_widget(table, area);
}

fn path_row<'a>(value: &'a CohortObserverProviderEvidence, app: &App) -> Row<'a> {
    let mut cells = vec![
        Cell::from(value.symbol.as_str()).style(app.theme.title),
        Cell::from(provider_alias(&value.strategy_id)),
        Cell::from(format!(
            "{}/{}",
            value.readiness_evaluations, value.eligible_signals
        )),
    ];
    cells.extend(HORIZONS.map(|horizon| {
        let evidence = value.paths.get(&horizon);
        Cell::from(path_label(evidence)).style(path_style(evidence, app))
    }));
    Row::new(cells)
}

fn path_label(value: Option<&CohortObserverPathEvidence>) -> String {
    let Some(evidence) = value else {
        return "N/A".into();
    };
    match (
        evidence.mean_directional_return_bps,
        evidence.positive_directional_rate,
    ) {
        (Some(mean), Some(rate)) => format!(
            "R{}/I{} {mean:+.1} {:.0}%",
            evidence.resolved,
            evidence.independent,
            rate * 100.0
        ),
        _ if evidence.missing_data > 0 => format!(
            "R{}/I{} GAP{}",
            evidence.resolved, evidence.independent, evidence.missing_data
        ),
        _ => format!(
            "R{}/I{} C{}",
            evidence.resolved, evidence.independent, evidence.censored
        ),
    }
}

fn path_style(value: Option<&CohortObserverPathEvidence>, app: &App) -> ratatui::style::Style {
    match value.and_then(|evidence| evidence.mean_directional_return_bps) {
        Some(mean) if mean > 0.0 => app.theme.bull,
        Some(mean) if mean < 0.0 => app.theme.bear,
        Some(_) => app.theme.muted,
        None => app.theme.gold,
    }
}

fn ordered_journal(app: &App) -> Vec<&CohortObserverProviderEvidence> {
    let journal = &app.backend.cohort_checkpoint.observer_provider_journal;
    let mut output = Vec::with_capacity(journal.len());
    for provider in &app.backend.cohort.providers {
        for symbol in &provider.symbols {
            if let Some(value) = journal
                .iter()
                .find(|value| value.strategy_id == provider.strategy_id && value.symbol == *symbol)
            {
                output.push(value);
            }
        }
    }
    for value in journal {
        let already_present = output.iter().any(|existing| {
            existing.strategy_id == value.strategy_id && existing.symbol == value.symbol
        });
        if !already_present {
            output.push(value);
        }
    }
    output
}
