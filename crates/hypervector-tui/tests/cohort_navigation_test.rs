use crossterm::event::{
    Event, KeyCode, KeyEvent, KeyModifiers, MouseButton, MouseEvent, MouseEventKind,
};
use hypervector_tui::cohort_navigation::resolve_tab_navigation;

fn key(code: KeyCode) -> Event {
    Event::Key(KeyEvent::new(code, KeyModifiers::NONE))
}

fn left_click(column: u16, row: u16) -> Event {
    Event::Mouse(MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column,
        row,
        modifiers: KeyModifiers::NONE,
    })
}

#[test]
fn number_keys_select_every_screen() {
    for (key_code, expected) in [
        ('1', 0),
        ('2', 1),
        ('3', 2),
        ('4', 3),
        ('5', 4),
        ('6', 5),
        ('7', 6),
        ('8', 7),
        ('9', 8),
    ] {
        assert_eq!(
            resolve_tab_navigation(&key(KeyCode::Char(key_code)), 1, true),
            Some(expected),
        );
    }
}

#[test]
fn tab_cycles_across_all_nine_screens() {
    for (current, expected) in [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 8),
        (8, 0),
    ] {
        assert_eq!(
            resolve_tab_navigation(&key(KeyCode::Tab), current, true),
            Some(expected),
        );
    }
}

#[test]
fn cohort_header_clicks_select_every_screen() {
    for (column, expected) in [
        (5, 0),
        (18, 1),
        (33, 2),
        (47, 3),
        (62, 4),
        (74, 5),
        (86, 6),
        (98, 7),
        (112, 8),
    ] {
        assert_eq!(
            resolve_tab_navigation(&left_click(column, 2), 1, true),
            Some(expected),
        );
    }
}

#[test]
fn mouse_navigation_rejects_non_tabs_and_non_cohort_views() {
    assert_eq!(resolve_tab_navigation(&left_click(12, 2), 1, true), None);
    assert_eq!(resolve_tab_navigation(&left_click(5, 1), 1, true), None);
    assert_eq!(resolve_tab_navigation(&left_click(5, 2), 1, false), None);
}
