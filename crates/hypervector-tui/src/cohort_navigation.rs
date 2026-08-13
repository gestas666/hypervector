//! Pure tab-navigation resolution for the nine-screen operator shell.

use crossterm::event::{Event, KeyCode, KeyEventKind, MouseButton, MouseEvent, MouseEventKind};

const TAB_COUNT: usize = 9;
const NAVIGATION_ROW: u16 = 2;
const NAVIGATION_START_COLUMN: u16 = 1;
const TAB_HORIZONTAL_PADDING: u16 = 2;
const TAB_DIVIDER_WIDTH: u16 = 3;
const TAB_TITLES: [&str; TAB_COUNT] = [
    "[1] PORT",
    "[2] SETUP",
    "[3] CHART",
    "[4] DEPTH",
    "[5] TRADE",
    "[6] LOG",
    "[7] OPS",
    "[8] REGIME",
    "[9] CFG",
];

/// Resolve a keyboard or cohort-header mouse event into a zero-based screen index.
pub fn resolve_tab_navigation(
    event: &Event,
    current_tab: usize,
    cohort_mouse_enabled: bool,
) -> Option<usize> {
    match event {
        Event::Key(key) if key.kind == KeyEventKind::Press => match key.code {
            KeyCode::Tab => Some((current_tab + 1) % TAB_COUNT),
            KeyCode::Char('1') => Some(0),
            KeyCode::Char('2') => Some(1),
            KeyCode::Char('3') => Some(2),
            KeyCode::Char('4') => Some(3),
            KeyCode::Char('5') => Some(4),
            KeyCode::Char('6') => Some(5),
            KeyCode::Char('7') => Some(6),
            KeyCode::Char('8') => Some(7),
            KeyCode::Char('9') => Some(8),
            _ => None,
        },
        Event::Mouse(mouse) if cohort_mouse_enabled => tab_from_mouse(*mouse),
        _ => None,
    }
}

fn tab_from_mouse(mouse: MouseEvent) -> Option<usize> {
    if mouse.row != NAVIGATION_ROW || mouse.kind != MouseEventKind::Down(MouseButton::Left) {
        return None;
    }
    let mut start = NAVIGATION_START_COLUMN;
    for (index, title) in TAB_TITLES.iter().enumerate() {
        let width = title.len() as u16 + TAB_HORIZONTAL_PADDING;
        if (start..start + width).contains(&mouse.column) {
            return Some(index);
        }
        start += width + TAB_DIVIDER_WIDTH;
    }
    None
}
