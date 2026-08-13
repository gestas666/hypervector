//! Composite risk, performance, lifecycle, and fill trading workspace.

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
};

use crate::app::App;

const TALL_TRADE_WORKSPACE_HEIGHT: u16 = 40;
const PERFORMANCE_VISUAL_HEIGHT: u16 = 12;
const POSITION_TABLE_CHROME_ROWS: u16 = 3;
const MINIMUM_POSITION_TRACKER_HEIGHT: u16 = 8;

/// Render a backend-authored trade command center without local simulation.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    if area.height >= TALL_TRADE_WORKSPACE_HEIGHT {
        render_tall(frame, app, area);
        return;
    }
    let sections = Layout::vertical([
        Constraint::Length(position_tracker_height(app)),
        Constraint::Length(7),
        Constraint::Min(8),
    ])
    .split(area);
    crate::cohort_trades::render_position_tracker(frame, app, sections[0]);
    crate::cohort_trade_performance::render(frame, app, sections[1]);
    let journals = Layout::vertical([Constraint::Percentage(55), Constraint::Percentage(45)])
        .split(sections[2]);
    crate::cohort_trade_history::render(frame, app, journals[0]);
    crate::cohort_trades::render_fill_journal(frame, app, journals[1]);
}

fn render_tall(frame: &mut Frame, app: &App, area: Rect) {
    let sections = Layout::vertical([
        Constraint::Length(position_tracker_height(app)),
        Constraint::Length(7),
        Constraint::Length(PERFORMANCE_VISUAL_HEIGHT),
        Constraint::Min(8),
    ])
    .split(area);
    crate::cohort_trades::render_position_tracker(frame, app, sections[0]);
    crate::cohort_trade_performance::render(frame, app, sections[1]);
    crate::cohort_performance_visuals::render(frame, app, sections[2]);
    let journals = Layout::vertical([Constraint::Percentage(55), Constraint::Percentage(45)])
        .split(sections[3]);
    crate::cohort_trade_history::render(frame, app, journals[0]);
    crate::cohort_trades::render_fill_journal(frame, app, journals[1]);
}

fn position_tracker_height(app: &App) -> u16 {
    u16::try_from(app.backend.cohort.assets.len())
        .unwrap_or(u16::MAX)
        .saturating_add(POSITION_TABLE_CHROME_ROWS)
        .max(MINIMUM_POSITION_TRACKER_HEIGHT)
}
