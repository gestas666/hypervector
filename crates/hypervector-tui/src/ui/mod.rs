//! Four-screen read-only renderer for authoritative backend telemetry.

mod dashboard;
mod header;
mod logs;
mod overlays;
mod policy_panels;
mod regime;
mod regime_widgets;
mod time;

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout},
};

use crate::app::App;

pub use time::{format_time_display, format_timestamp_display};

/// Render the active read-only telemetry screen and any requested overlay.
pub fn draw(f: &mut Frame, app: &App) {
    if app.backend.is_multi_asset_cohort() {
        crate::cohort_view::render(f, app);
        return;
    }
    if app.snapshots.is_empty() {
        header::render_backend_only(f, app);
        return;
    }
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Length(3),
            Constraint::Min(20),
            Constraint::Length(3),
        ])
        .split(f.area());

    header::render_header(f, app, chunks[0]);
    header::render_timeline_ribbon(f, app, chunks[1]);
    render_active_screen(f, app, chunks[2]);
    overlays::render_footer(f, app, chunks[3]);
    overlays::render_requested_overlays(f, app);
}

fn render_active_screen(f: &mut Frame, app: &App, area: ratatui::layout::Rect) {
    match app.active_tab {
        0 => dashboard::render(f, app, area),
        1 => regime::render(f, app, area),
        2 => crate::chart_view::render_backend_chart(f, app, area),
        _ => crate::config_view::render_backend_configuration(f, app, area),
    }
}
