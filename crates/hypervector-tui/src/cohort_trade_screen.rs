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
    let performance_height = short_performance_height(app, area.height, area.width);
    let sections = Layout::vertical([
        Constraint::Length(position_tracker_height(app)),
        Constraint::Length(performance_height),
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

fn short_performance_height(app: &App, area_height: u16, area_width: u16) -> u16 {
    let available = area_height
        .saturating_sub(position_tracker_height(app))
        .saturating_sub(8);
    let preferred = crate::cohort_trade_performance::preferred_height(app, area_width);
    if preferred <= available {
        return preferred;
    }
    crate::cohort_trade_performance::compact_height(app)
        .min(available)
        .max(3)
}

fn render_tall(frame: &mut Frame, app: &App, area: Rect) {
    let performance_height = available_performance_height(app, area.height, area.width);
    let sections = Layout::vertical([
        Constraint::Length(position_tracker_height(app)),
        Constraint::Length(performance_height),
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

fn available_performance_height(app: &App, area_height: u16, area_width: u16) -> u16 {
    let reserved = position_tracker_height(app)
        .saturating_add(PERFORMANCE_VISUAL_HEIGHT)
        .saturating_add(8);
    crate::cohort_trade_performance::preferred_height(app, area_width)
        .min(area_height.saturating_sub(reserved).max(7))
}

fn position_tracker_height(app: &App) -> u16 {
    u16::try_from(app.backend.cohort.assets.len())
        .unwrap_or(u16::MAX)
        .saturating_add(POSITION_TABLE_CHROME_ROWS)
        .max(MINIMUM_POSITION_TRACKER_HEIGHT)
}
