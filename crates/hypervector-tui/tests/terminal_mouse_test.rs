use hypervector_tui::terminal_mouse::mouse_reset_sequence;

#[test]
fn terminal_startup_resets_every_mouse_tracking_mode() {
    let encoded = mouse_reset_sequence();

    assert_eq!(
        encoded,
        concat!(
            "\u{1b}[?1016l\u{1b}[?1015l\u{1b}[?1006l\u{1b}[?1005l",
            "\u{1b}[?1003l\u{1b}[?1002l\u{1b}[?1000l\u{1b}[?9l",
        )
    );
    assert!(!encoded.contains('h'));
}
