//! Ops Floor layout — mode banner, gates|book, regime|tape, health footer.

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::widgets::TableState;
use ratatui::Frame;

use crate::model::{AppSnapshot, CardId};
use crate::theme::Theme;
use crate::ui::cards::{book_card, gates, health, mode_banner, regime, tape};

pub fn render_floor(
    frame: &mut Frame,
    area: Rect,
    snap: &AppSnapshot,
    theme: &Theme,
    focus_card: CardId,
    tape_state: &mut TableState,
) {
    // Vertical: banner (3) → mid → footer (3)
    let cols = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Percentage(32),
            Constraint::Min(8),
            Constraint::Length(3),
        ])
        .split(area);

    mode_banner::render(frame, cols[0], snap, theme);

    // Mid: gates | book
    let mid = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(48), Constraint::Percentage(52)])
        .split(cols[1]);
    gates::render(frame, mid[0], snap, theme, focus_card == CardId::Gates);
    book_card::render(frame, mid[1], snap, theme, focus_card == CardId::Book);

    // Lower: regime | tape
    let low = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
        .split(cols[2]);
    regime::render(frame, low[0], snap, theme, focus_card == CardId::Regime);
    tape::render(
        frame,
        low[1],
        snap,
        theme,
        focus_card == CardId::Tape,
        tape_state,
    );

    health::render(frame, cols[3], snap, theme, focus_card == CardId::Health);
}
