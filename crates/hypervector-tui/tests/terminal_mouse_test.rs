use hypervector_tui::terminal_mouse::click_capture_sequence;

#[test]
fn click_capture_omits_drag_and_motion_tracking_modes() {
    let encoded = click_capture_sequence();

    assert_eq!(encoded, "\u{1b}[?1000h\u{1b}[?1006h");
    assert!(!encoded.contains("?1002h"));
    assert!(!encoded.contains("?1003h"));
}
