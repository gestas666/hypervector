//! Terminal mouse-mode commands constrained to click events.

/// Enable button press/release events with SGR coordinates, excluding motion modes.
pub const fn click_capture_sequence() -> &'static str {
    "\u{1b}[?1000h\u{1b}[?1006h"
}
