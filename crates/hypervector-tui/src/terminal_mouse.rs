//! Terminal mouse-mode reset commands for a keyboard-driven cockpit.

/// Disable every mouse reporting mode accepted by supported xterm terminals.
pub const fn mouse_reset_sequence() -> &'static str {
    concat!(
        "\u{1b}[?1016l\u{1b}[?1015l\u{1b}[?1006l\u{1b}[?1005l",
        "\u{1b}[?1003l\u{1b}[?1002l\u{1b}[?1000l\u{1b}[?9l",
    )
}
