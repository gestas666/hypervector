//! Adaptive multi-row meters for high-signal cohort telemetry.

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
    style::Style,
    symbols,
    text::{Line, Span},
    widgets::{LineGauge, Paragraph},
};

use crate::app::App;

/// Render a labeled block meter when height permits, with a compact fallback.
pub(crate) fn render(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    label: String,
    ratio: Option<f64>,
    filled_style: Style,
) {
    let value = ratio.unwrap_or(0.0).clamp(0.0, 1.0);
    let active_style = if ratio.is_some() {
        filled_style
    } else {
        app.theme.muted
    };
    if area.height < 2 {
        frame.render_widget(
            LineGauge::default()
                .style(app.theme.muted)
                .filled_style(active_style)
                .unfilled_style(app.theme.bar_ghost)
                .line_set(symbols::line::THICK)
                .ratio(value)
                .label(label),
            area,
        );
        return;
    }
    let rows = Layout::vertical([Constraint::Length(1), Constraint::Min(1)]).split(area);
    frame.render_widget(Paragraph::new(Span::styled(label, active_style)), rows[0]);
    render_block_rows(frame, rows[1], value, active_style, app.theme.bar_ghost);
}

fn render_block_rows(
    frame: &mut Frame,
    area: Rect,
    ratio: f64,
    filled_style: Style,
    ghost_style: Style,
) {
    let width = usize::from(area.width);
    let filled = ((width as f64) * ratio).round() as usize;
    let row = Line::from(vec![
        Span::styled("█".repeat(filled.min(width)), filled_style),
        Span::styled("░".repeat(width.saturating_sub(filled)), ghost_style),
    ]);
    frame.render_widget(Paragraph::new(vec![row; usize::from(area.height)]), area);
}
