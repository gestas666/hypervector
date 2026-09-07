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
    frame.render_widget(Clear, area);
    let block =
        panel(title, app).title_bottom(" [Up/Down PgUp/PgDn Home/End] SCROLL [Enter/Esc] CLOSE ");
    let inner = block.inner(area);
    let paragraph = Paragraph::new(lines).wrap(Wrap { trim: true });
    let maximum = paragraph
        .line_count(inner.width)
        .saturating_sub(usize::from(inner.height));
    let maximum = u16::try_from(maximum).unwrap_or(u16::MAX);
    app.cohort_detail_max_scroll.set(maximum);
    frame.render_widget(block, area);
    frame.render_widget(
        paragraph.scroll((app.cohort_detail_scroll.min(maximum), 0)),
        inner,
    );
}
