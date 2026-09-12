//! Shared bounded scrolling for exact backend evidence inspectors.

use crate::{app::App, cohort_widgets::panel};
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::Rect,
    text::Line,
    widgets::{Clear, Paragraph, Wrap},
};

const PAGE_ROWS: u16 = 10;

impl App {
    /// Scroll the active evidence inspector using its actual wrapped content height.
    pub fn handle_cohort_detail_scroll(&mut self, key: KeyCode) {
        let maximum = self.cohort_detail_max_scroll.get();
        let current = self.cohort_detail_scroll.min(maximum);
        self.cohort_detail_scroll = match key {
            KeyCode::Down => current.saturating_add(1),
            KeyCode::Up => current.saturating_sub(1),
            KeyCode::PageDown => current.saturating_add(PAGE_ROWS),
            KeyCode::PageUp => current.saturating_sub(PAGE_ROWS),
            KeyCode::Home => 0,
            KeyCode::End => maximum,
            _ => current,
        }
        .min(maximum);
    }
}

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect, title: &str, lines: Vec<Line<'_>>) {
    render_with_controls(
        frame,
        app,
        area,
        title,
        lines,
        " [Up/Down PgUp/PgDn Home/End] SCROLL [Enter/Esc] CLOSE ",
    );
}

/// Render bounded wrapped evidence with controls suited to the panel width.
pub(crate) fn render_with_controls(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    title: &str,
    lines: Vec<Line<'_>>,
    controls: &'static str,
) {
    frame.render_widget(Clear, area);
    let block = panel(title, app).title_bottom(controls);
    let inner = block.inner(area);
    let (paragraph, _, maximum) =
        bounded_paragraph(lines, inner.width, inner.height, app.cohort_detail_scroll);
    app.cohort_detail_max_scroll.set(maximum);
    frame.render_widget(block, area);
    frame.render_widget(paragraph, inner);
}

/// Wrap evidence and clamp its viewport to the actual terminal-row extent.
pub(crate) fn bounded_paragraph(
    lines: Vec<Line<'_>>,
    width: u16,
    height: u16,
    offset: u16,
) -> (Paragraph<'_>, usize, u16) {
    let paragraph = Paragraph::new(lines).wrap(Wrap { trim: true });
    let total = paragraph.line_count(width);
    let maximum = u16::try_from(total.saturating_sub(usize::from(height))).unwrap_or(u16::MAX);
    (paragraph.scroll((offset.min(maximum), 0)), total, maximum)
}
